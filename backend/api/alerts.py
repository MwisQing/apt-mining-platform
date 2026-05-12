import hashlib
import io
import json
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from backend.services import _build_trace_index, compute_badges
from backend.services.snapshot_builder import (
    SNAPSHOT_STATUS_BUILDING,
    SNAPSHOT_TYPE_ALERT_CANDIDATES,
    get_active_snapshot_version,
    get_snapshot_meta,
    rebuild_candidate_snapshots_async,
)
from backend.services.alert_workbench import (
    DEFAULT_CANDIDATE_RULES,
    build_candidate_rule_sql,
    build_candidate_reason_labels,
    classify_target_kind,
    classify_candidate_priority,
    compute_candidate_score,
    detect_candidate_matches,
    split_multi_values,
)
from backend.utils import get_config
from backend.utils.db import get_db


router = APIRouter(prefix="/api/alerts", tags=["alerts"])
candidate_router = APIRouter(prefix="/api/alert-candidates", tags=["alert-candidates"])

# In-process cache for fully-decorated candidate data.
# Key = hash of filter params (excl. sort/page/date), value = {items, total, ts}.
_candidate_cache = OrderedDict()
# Full-range cache: bucketed by base filter params and stores ALL decorated
# candidate items without date/keyword/badge/target-kind filtering.
_full_cache = OrderedDict()  # key -> {items, total, ts, sorted_views}
CACHE_MAX_ENTRIES = 20
CACHE_TTL = 600  # 10 minutes
FULL_CACHE_TTL = 300  # 5 minutes for full cache
FULL_CACHE_MAX_ENTRIES = 12
SQLITE_IN_LIMIT_SAFE = 800


def _cache_key_for_params(params: dict) -> str:
    filter_params = {
        k: v for k, v in sorted(params.items())
        if k not in ("sort_by", "sort_order", "page", "page_size", "date_start", "date_end")
    }
    raw = json.dumps(filter_params, default=str, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _full_cache_key_for_params(params: dict) -> str:
    filter_params = {
        k: v for k, v in sorted(params.items())
        if k not in (
            "sort_by",
            "sort_order",
            "page",
            "page_size",
            "date_start",
            "date_end",
            "keyword",
            "badges_filter",
            "target_kind",
        )
    }
    raw = json.dumps(filter_params, default=str, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _evict_cache_if_needed():
    now = time.time()
    expired = [k for k, v in _candidate_cache.items() if now - v["ts"] > CACHE_TTL]
    for k in expired:
        del _candidate_cache[k]
    while len(_candidate_cache) > CACHE_MAX_ENTRIES:
        _candidate_cache.popitem(last=False)


def _invalidate_full_cache():
    """Invalidate the full-range cache. Called on data mutations."""
    _full_cache.clear()


def _evict_full_cache_if_needed():
    now = time.time()
    expired = [k for k, v in _full_cache.items() if now - v["ts"] > FULL_CACHE_TTL]
    for k in expired:
        del _full_cache[k]
    while len(_full_cache) > FULL_CACHE_MAX_ENTRIES:
        _full_cache.popitem(last=False)


def _iter_chunks(values, size=SQLITE_IN_LIMIT_SAFE):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _filter_by_date(items, date_start, date_end):
    """Filter candidate items by date range in Python."""
    if not date_start and not date_end:
        return items
    filtered = []
    for item in items:
        fat = item.get("first_alert_time") or ""
        if date_start and fat < f"{date_start} 00:00:00":
            continue
        if date_end and fat > f"{date_end} 23:59:59":
            continue
        filtered.append(item)
    return filtered


def _filter_by_keyword(items, keyword):
    if not keyword:
        return items
    lowered_keyword = keyword.lower()
    keyword_fields = ("device_id", "source_ip", "target", "threat_type", "apt_org", "std_apt_org")
    return [
        item
        for item in items
        if any(lowered_keyword in str(item.get(field) or "").lower() for field in keyword_fields)
    ]


def _filter_by_target_kind(items, target_kind):
    if not target_kind or target_kind == "all":
        return items
    return [
        item
        for item in items
        if item.get("target_kind") == target_kind
        or classify_target_kind(item.get("target"), item.get("target_type")) == target_kind
    ]


def _filter_by_badges(items, badges_filter):
    required_badges = set(_csv_values(badges_filter))
    if not required_badges:
        return items
    return [
        item
        for item in items
        if required_badges.issubset({badge.get("name") for badge in (item.get("badges") or [])})
    ]


def _csv_values(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _split_multi_values(value):
    return split_multi_values(value)


def _build_where(
    *,
    date_start=None,
    date_end=None,
    target_type=None,
    device_tags=None,
    exclude_device_tags=None,
    threat_types=None,
    threat_levels=None,
    apt_tiers=None,
    hide_traced=True,
    hide_closed=True,
    keyword=None,
    alert_count_max=None,
):
    conditions = []
    params = {}

    if date_start:
        conditions.append("a.first_alert_time >= :date_start")
        params["date_start"] = f"{date_start} 00:00:00"
    if date_end:
        conditions.append("a.first_alert_time <= :date_end_end")
        params["date_end_end"] = f"{date_end} 23:59:59"
    if target_type:
        conditions.append("a.target_type = :target_type")
        params["target_type"] = target_type

    selected_threat_types = _csv_values(threat_types)
    if selected_threat_types:
        clauses = []
        for index, item in enumerate(selected_threat_types):
            key = f"tt_{index}"
            clauses.append(f"COALESCE(a.threat_type, '') LIKE :{key}")
            params[key] = f"%{item}%"
        conditions.append("(" + " OR ".join(clauses) + ")")

    levels = _csv_values(threat_levels)
    if levels:
        placeholders = ", ".join(f":tl_{index}" for index in range(len(levels)))
        conditions.append(f"a.threat_level IN ({placeholders})")
        for index, level in enumerate(levels):
            params[f"tl_{index}"] = level

    tiers = _csv_values(apt_tiers)
    if tiers:
        placeholders = ", ".join(f":at_{index}" for index in range(len(tiers)))
        conditions.append(f"a.apt_org_tier IN ({placeholders})")
        for index, tier in enumerate(tiers):
            params[f"at_{index}"] = tier

    tag_ids = _csv_values(device_tags)
    if tag_ids:
        placeholders = ", ".join(f":tag_{index}" for index in range(len(tag_ids)))
        conditions.append(
            "EXISTS ("
            "  SELECT 1 FROM device_tags dt "
            f"  WHERE dt.device_id = a.device_id AND dt.tag_id IN ({placeholders})"
            ")"
        )
        for index, tag_id in enumerate(tag_ids):
            params[f"tag_{index}"] = tag_id

    exclude_tag_ids = _csv_values(exclude_device_tags)
    if exclude_tag_ids:
        placeholders = ", ".join(f":et_{index}" for index in range(len(exclude_tag_ids)))
        conditions.append(
            "NOT EXISTS ("
            "  SELECT 1 FROM device_tags dt "
            f"  WHERE dt.device_id = a.device_id AND dt.tag_id IN ({placeholders})"
            ")"
        )
        for index, tag_id in enumerate(exclude_tag_ids):
            params[f"et_{index}"] = tag_id

    if alert_count_max is not None:
        conditions.append("a.alert_count <= :alert_count_max")
        params["alert_count_max"] = alert_count_max

    if keyword:
        keyword_like = f"%{keyword}%"
        conditions.append(
            "(a.device_id LIKE :kw OR a.source_ip LIKE :kw OR a.target LIKE :kw "
            "OR a.threat_type LIKE :kw OR a.apt_org LIKE :kw OR a.std_apt_org LIKE :kw)"
        )
        params["kw"] = keyword_like

    cfg = get_config()
    ttl_days = cfg.get("rules", {}).get("trace_ttl_days", 30)
    if hide_traced:
        conditions.append(
            "NOT EXISTS ("
            "  SELECT 1 FROM traced_targets tt "
            "  WHERE tt.target = a.target "
            "  AND COALESCE(tt.port, '') IN ('', COALESCE(a.port, '')) "
            f"  AND (tt.traced_at IS NULL OR tt.traced_at >= datetime('now', '-{ttl_days} days'))"
            ")"
        )

    return " AND ".join(conditions) if conditions else "1=1", params


def _cross_day_and_lateral(db, where, params, *, need_cross_day=True, need_lateral=True):
    cross_day_pairs = set()
    lateral_ips = set()

    if need_cross_day:
        rows = db.execute(
            text(
                f"""
                SELECT a.source_ip, a.target
                FROM alerts a
                WHERE {where}
                GROUP BY a.source_ip, a.target
                HAVING COUNT(DISTINCT DATE(a.first_alert_time)) >= 2
                """
            ),
            params,
        ).fetchall()
        cross_day_pairs = {(row[0], row[1]) for row in rows}

    if need_lateral:
        rows = db.execute(
            text(
                f"""
                SELECT a.source_ip
                FROM alerts a
                WHERE {where}
                GROUP BY a.source_ip
                HAVING COUNT(DISTINCT a.target) >= 3
                """
            ),
            params,
        ).fetchall()
        lateral_ips = {row[0] for row in rows}

    return cross_day_pairs, lateral_ips


def _fake_row(row_dict):
    class FakeRow:
        pass

    fake = FakeRow()
    for key, value in row_dict.items():
        setattr(fake, key, value)
    return fake


def _stringify_datetimes(row_dict):
    for key in ("first_alert_time", "last_alert_time", "imported_at"):
        if key in row_dict and row_dict[key]:
            row_dict[key] = str(row_dict[key])


def _dedupe_badges(badges):
    deduped = []
    seen = set()
    for badge in badges:
        name = badge.get("name") or ""
        label = badge.get("label") or ""
        signature = (name, label)
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(badge)
    return deduped


def _event_rank(status):
    return {"active": 0, "confirmed": 1, "unconfirmed": 2}.get(status or "", 99)


def _prefer_event(current, candidate):
    if current is None:
        return candidate
    current_key = (_event_rank(current.get("status")), current.get("mined_at") or "")
    candidate_key = (_event_rank(candidate.get("status")), candidate.get("mined_at") or "")
    return candidate if candidate_key < current_key else current


def _preload_trace_index(db):
    """Preload ALL traced_targets into an index for O(1) badge lookup."""
    trace_rows = db.execute(text(
        "SELECT target, COALESCE(port, '') AS port, traced_at, note FROM traced_targets"
    )).fetchall()
    return _build_trace_index(trace_rows)


def _event_maps_for_rows(db, rows):
    """Build IOC→event maps. Events are matched by IOC+port only, not by device_id."""
    targets = sorted({row._mapping["target"] for row in rows if row._mapping.get("target")})

    ioc_exact_map = {}
    ioc_wildcard_map = {}

    if targets:
        for chunk in _iter_chunks(targets):
            placeholders = ", ".join(f":target_{index}" for index in range(len(chunk)))
            ioc_rows = db.execute(
                text(
                    f"""
                    SELECT
                        mei.target,
                        COALESCE(mei.port, '') AS port,
                        me.id AS event_id,
                        me.event_name,
                        me.color,
                        me.status,
                        me.mined_at
                    FROM mined_event_iocs mei
                    JOIN mined_events me ON me.id = mei.event_id
                    WHERE mei.target IN ({placeholders})
                    """
                ),
                {f"target_{index}": value for index, value in enumerate(chunk)},
            ).fetchall()
            for row in ioc_rows:
                event_info = {
                    "event_id": row[2],
                    "event_name": row[3],
                    "color": row[4],
                    "status": row[5],
                    "mined_at": str(row[6]) if row[6] else None,
                }
                if row[1]:
                    key = (row[0], row[1])
                    ioc_exact_map[key] = _prefer_event(ioc_exact_map.get(key), event_info)
                else:
                    ioc_wildcard_map[row[0]] = _prefer_event(ioc_wildcard_map.get(row[0]), event_info)

    return {}, ioc_exact_map, ioc_wildcard_map


def _parse_datetime_like(value):
    if not value:
        return None
    text_value = str(value).strip().replace(" ", "T")
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        candidates = [text_value, text_value[:19], text_value[:10]]
        for candidate in candidates:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    return datetime.strptime(candidate, fmt)
                except ValueError:
                    continue
    return None


def _trace_maps_for_rows(db, rows):
    targets = sorted({row._mapping["target"] for row in rows if row._mapping.get("target")})
    exact_map = {}
    wildcard_map = {}
    if not targets:
        return exact_map, wildcard_map

    for chunk in _iter_chunks(targets):
        placeholders = ", ".join(f":target_{index}" for index in range(len(chunk)))
        trace_rows = db.execute(
            text(
                f"""
                SELECT target, COALESCE(port, '') AS port, traced_at, note
                FROM traced_targets
                WHERE target IN ({placeholders})
                ORDER BY COALESCE(traced_at, '9999-12-31T00:00:00') DESC
                """
            ),
            {f"target_{index}": value for index, value in enumerate(chunk)},
        ).fetchall()

        for row in trace_rows:
            trace_info = {
                "target": row[0],
                "port": row[1],
                "traced_at": str(row[2]) if row[2] else None,
                "note": row[3],
            }
            if row[1]:
                exact_map.setdefault((row[0], row[1]), trace_info)
            else:
                wildcard_map.setdefault(row[0], trace_info)

    return exact_map, wildcard_map


def _trace_info_for_row(row_dict, exact_map, wildcard_map):
    cfg = get_config()
    ttl_days = cfg.get("rules", {}).get("trace_ttl_days", 30)
    port = row_dict.get("port") or ""
    trace_info = exact_map.get((row_dict.get("target"), port)) or wildcard_map.get(row_dict.get("target"))
    if not trace_info:
        return None

    traced_at = _parse_datetime_like(trace_info.get("traced_at"))
    active = traced_at is None or traced_at >= datetime.now() - timedelta(days=ttl_days)
    result = dict(trace_info)
    result["active"] = active
    result["label"] = "追踪过"
    return result


def _device_tag_map_for_rows(db, rows):
    device_ids = sorted({row._mapping["device_id"] for row in rows if row._mapping.get("device_id")})
    tag_map = {device_id: [] for device_id in device_ids}
    if not device_ids:
        return tag_map

    for chunk in _iter_chunks(device_ids):
        placeholders = ", ".join(f":device_{index}" for index in range(len(chunk)))
        tag_rows = db.execute(
            text(
                f"""
                SELECT
                    dt.device_id,
                    t.id,
                    t.name,
                    t.color,
                    t.is_permanent,
                    t.batch_id
                FROM device_tags dt
                JOIN tags t ON t.id = dt.tag_id
                LEFT JOIN tag_batches tb ON tb.id = t.batch_id
                WHERE dt.device_id IN ({placeholders})
                AND (t.batch_id IS NULL OR tb.status IS NULL OR tb.status != 'deleted')
                ORDER BY t.created_at DESC, t.id DESC
                """
            ),
            {f"device_{index}": value for index, value in enumerate(chunk)},
        ).fetchall()

        for row in tag_rows:
            device_id = row[0]
            tag_id = row[1]
            tag_name = (row[2] or "").strip()
            # Guard against duplicate tag_id AND duplicate tag name (normalized)
            if any(t["id"] == tag_id or t["name"].strip() == tag_name for t in tag_map[device_id]):
                continue
            tag_map[device_id].append(
                {
                    "id": tag_id,
                    "name": row[2],
                    "color": row[3],
                    "is_permanent": bool(row[4]),
                    "batch_id": row[5],
                }
            )

    return tag_map


def _build_relation_badges(row_dict, device_tags, event_info, trace_info):
    badges = []

    if event_info:
        badges.append(
            {
                "name": f"event:{event_info['event_id']}",
                "label": f"事件:{event_info['event_name']}",
                "color": event_info.get("color") or "#409EFF",
            }
        )

    for tag in device_tags:
        badges.append(
            {
                "name": f"device_tag:{tag['id']}",
                "label": f"标签:{tag['name']}",
                "color": tag.get("color") or "#909399",
            }
        )

    if trace_info:
        note_preview = trace_info.get("note", "")
        label = f"IOC备注:{note_preview}" if note_preview else "IOC备注:有记录"
        badges.append({"name": "traced_history", "label": label, "color": "#13c2c2"})

    for threat_type in _split_multi_values(row_dict.get("threat_type")):
        badges.append({
            "name": f"meta:threat_type:{threat_type}",
            "label": f"威胁:{threat_type}",
            "color": "#6f42c1",
        })

    std_apt_org = row_dict.get("std_apt_org")
    if std_apt_org:
        badges.append({
            "name": f"meta:std_apt_org:{std_apt_org}",
            "label": f"标准APT:{std_apt_org}",
            "color": "#d9485f",
        })

    apt_org = row_dict.get("apt_org")
    if apt_org:
        badges.append({
            "name": f"meta:apt_org:{apt_org}",
            "label": f"APT:{apt_org}",
            "color": "#fa8c16",
        })

    for vendor in _split_multi_values(row_dict.get("vendors")):
        badges.append({
            "name": f"meta:vendor:{vendor}",
            "label": f"厂商:{vendor}",
            "color": "#595959",
        })

    return badges


def _resolve_hide_defaults(hide_traced, hide_closed):
    cfg = get_config()
    rules = cfg.get("rules", {})
    resolved_hide_traced = (
        rules.get("default_hide_traced", True) if hide_traced is None else hide_traced
    )
    resolved_hide_closed = (
        rules.get("default_hide_closed_events", True) if hide_closed is None else hide_closed
    )
    return resolved_hide_traced, resolved_hide_closed


def _event_for_row(row_dict, device_map, ioc_exact_map, ioc_wildcard_map):
    """Match event by IOC+port only. device_map is kept for API compatibility but unused."""
    port = row_dict.get("port") or ""
    return (
        ioc_exact_map.get((row_dict.get("target"), port))
        or ioc_wildcard_map.get(row_dict.get("target"))
    )


def _make_items(db, rows, cross_day_pairs, lateral_ips, badges_filter=None, trace_index=None):
    device_map, ioc_exact_map, ioc_wildcard_map = _event_maps_for_rows(db, rows)
    trace_exact_map, trace_wildcard_map = _trace_maps_for_rows(db, rows)
    tag_map = _device_tag_map_for_rows(db, rows)

    items = []
    for row in rows:
        row_dict = dict(row._mapping)
        row_dict.pop("_rn", None)  # Remove dedup row-number from output
        event_info = _event_for_row(row_dict, device_map, ioc_exact_map, ioc_wildcard_map)
        trace_info = _trace_info_for_row(row_dict, trace_exact_map, trace_wildcard_map)
        device_tags = tag_map.get(row_dict.get("device_id"), [])

        row_dict["badges"] = _dedupe_badges(
            compute_badges(
                _fake_row(row_dict),
                cross_day_pairs,
                lateral_ips,
                trace_info=trace_info,
                trace_index=trace_index,
            )
            + _build_relation_badges(row_dict, device_tags, event_info, trace_info)
        )

        row_dict["device_tags"] = device_tags
        row_dict["event"] = event_info
        row_dict["traced"] = trace_info
        row_dict["ioc_note"] = trace_info.get("note") if trace_info else None
        row_dict["relation_summary"] = " | ".join(
            [badge["label"] for badge in _build_relation_badges(row_dict, device_tags, event_info, trace_info)]
        )
        _stringify_datetimes(row_dict)
        items.append(row_dict)
    return items


def _build_filter_options(items):
    """Extract unique filter values from ALL candidate items.

    Returns a dict of column key → sorted list of unique values.
    Called on the full cached item list, never triggers extra DB queries.
    """
    result = {}

    # device_tags: union of all tag names
    tag_names = set()
    for item in items:
        for tag in (item.get("device_tags") or []):
            tag_names.add(tag.get("name"))
    result["device_tags"] = sorted(tag_names)

    # threat_type
    result["threat_type"] = sorted({
        item.get("threat_type") for item in items
        if item.get("threat_type")
    })

    # std_apt_org
    result["std_apt_org"] = sorted({
        item.get("std_apt_org") for item in items
        if item.get("std_apt_org")
    })

    # priority: fixed three values
    result["priority"] = ["高优先", "中优先", "观察"]

    # port
    result["port"] = sorted({
        item.get("port") for item in items
        if item.get("port")
    })

    # badges: union of all badge labels
    badge_labels = set()
    for item in items:
        for badge in (item.get("badges") or []):
            badge_labels.add(badge.get("label"))
    result["badges"] = sorted(badge_labels)

    # ioc_note: text input filter, no options list
    result["ioc_note"] = None

    return result


def _snapshot_empty_filter_options():
    return {
        "device_tags": [],
        "threat_type": [],
        "std_apt_org": [],
        "priority": ["高优先", "中优先", "观察"],
        "port": [],
        "badges": [],
        "ioc_note": None,
    }


def _build_snapshot_filter_options(db, where, params):
    result = _snapshot_empty_filter_options()

    threat_rows = db.execute(
        text(
            f"SELECT DISTINCT s.threat_type FROM alert_candidate_snapshots s WHERE {where} "
            "AND COALESCE(s.threat_type, '') != '' ORDER BY s.threat_type"
        ),
        params,
    ).fetchall()
    result["threat_type"] = [row[0] for row in threat_rows]

    apt_rows = db.execute(
        text(
            f"SELECT DISTINCT s.std_apt_org FROM alert_candidate_snapshots s WHERE {where} "
            "AND COALESCE(s.std_apt_org, '') != '' ORDER BY s.std_apt_org"
        ),
        params,
    ).fetchall()
    result["std_apt_org"] = [row[0] for row in apt_rows]

    port_rows = db.execute(
        text(
            f"SELECT DISTINCT s.port FROM alert_candidate_snapshots s WHERE {where} "
            "AND COALESCE(s.port, '') != '' ORDER BY s.port"
        ),
        params,
    ).fetchall()
    result["port"] = [row[0] for row in port_rows]

    tag_rows = db.execute(
        text(
            "SELECT DISTINCT st.tag_name "
            "FROM alert_candidate_snapshot_tags st "
            "JOIN alert_candidate_snapshots s ON s.id = st.snapshot_id "
            f"WHERE {where} ORDER BY st.tag_name"
        ),
        params,
    ).fetchall()
    result["device_tags"] = [row[0] for row in tag_rows]

    badge_rows = db.execute(
        text(
            "SELECT DISTINCT sb.badge_label "
            "FROM alert_candidate_snapshot_badges sb "
            "JOIN alert_candidate_snapshots s ON s.id = sb.snapshot_id "
            f"WHERE {where} ORDER BY sb.badge_label"
        ),
        params,
    ).fetchall()
    result["badges"] = [row[0] for row in badge_rows]

    return result


def _snapshot_sort_clause(sort_field, sort_direction):
    direction = "ASC" if sort_direction == "ASC" else "DESC"
    mapping = {
        "candidate_score": f"s.candidate_score {direction}, s.last_alert_time DESC, s.id DESC",
        "device_id": f"COALESCE(s.device_id, '') COLLATE NOCASE {direction}, s.id DESC",
        "source_ip": f"COALESCE(s.source_ip, '') COLLATE NOCASE {direction}, s.id DESC",
        "target": f"COALESCE(s.target, '') COLLATE NOCASE {direction}, s.id DESC",
        "port": f"COALESCE(s.port, '') COLLATE NOCASE {direction}, s.id DESC",
        "threat_type": f"COALESCE(s.threat_type, '') COLLATE NOCASE {direction}, s.id DESC",
        "std_apt_org": f"COALESCE(s.std_apt_org, '') COLLATE NOCASE {direction}, s.id DESC",
        "analysis_status": f"COALESCE(s.analysis_status, '') COLLATE NOCASE {direction}, s.id DESC",
        "is_focused": f"COALESCE(s.is_focused, 0) {direction}, s.id DESC",
        "first_alert_time": f"COALESCE(s.first_alert_time, '') {direction}, s.id DESC",
        "last_alert_time": f"COALESCE(s.last_alert_time, '') {direction}, s.id DESC",
        "alert_count": f"COALESCE(s.alert_count, 0) {direction}, s.id DESC",
        "device_alert_count": f"COALESCE(s.heat_device_alert_count, 0) {direction}, s.id DESC",
        "device_target_count": f"COALESCE(s.heat_device_target_count, 0) {direction}, s.id DESC",
        "target_alert_count": f"COALESCE(s.heat_target_alert_count, 0) {direction}, s.id DESC",
        "target_device_count": f"COALESCE(s.heat_target_device_count, 0) {direction}, s.id DESC",
        "source_ip_count": f"COALESCE(s.source_ip_count, 0) {direction}, s.id DESC",
    }
    return mapping.get(sort_field, "s.candidate_score DESC, s.last_alert_time DESC, s.id DESC")


def _deserialize_snapshot_row(row_dict):
    item = dict(row_dict)
    item.pop("badges_json", None)
    item.pop("device_tags_json", None)
    item["badges"] = []
    item["device_tags"] = []
    item["event"] = json.loads(item.pop("event_json", "null") or "null")
    item["traced"] = json.loads(item.pop("trace_json", "null") or "null")
    item["candidate_rule_ids"] = json.loads(item.pop("candidate_rule_ids_json", "[]") or "[]")
    item["candidate_reasons"] = json.loads(item.pop("candidate_reasons_json", "[]") or "[]")
    item["heat_summary"] = json.loads(item.pop("heat_summary_json", "{}") or "{}")
    item["heat"] = {
        "target_alert_count": item.pop("heat_target_alert_count", 0),
        "target_device_count": item.pop("heat_target_device_count", 0),
        "device_alert_count": item.pop("heat_device_alert_count", 0),
        "device_target_count": item.pop("heat_device_target_count", 0),
        "source_ip_alert_count": item.pop("heat_source_ip_alert_count", 0),
    }
    item["sort_signals"] = {
        "priority_rank": item.pop("sort_priority_rank", 0),
        "rule_hits": item.pop("sort_rule_hits", 0),
        "target_device_count": item.pop("sort_target_device_count", 0),
        "target_alert_count": item.pop("sort_target_alert_count", 0),
        "source_ip_alert_count": item.pop("sort_source_ip_alert_count", 0),
        "trace_status": item.pop("sort_trace_status", None),
        "event_status": item.pop("sort_event_status", None),
    }
    item["candidate_priority"] = {
        "id": item.get("candidate_priority"),
        "label": item.get("candidate_priority_label"),
        "rank": item["sort_signals"]["priority_rank"],
    }
    item["trace_status_label"] = {
        "active": "追踪 TTL 内",
        "expired": "历史追踪",
    }.get(item.get("trace_status"), "未追踪")
    item["script_bucket"] = item.get("target_kind") if item.get("target_kind") in {"ip", "domain"} else "other"
    return item


def _attach_snapshot_relations(db, items, snapshot_version):
    if not items:
        return items
    snapshot_ids = [item.get("id") for item in items if item.get("id") is not None]
    if not snapshot_ids:
        return items

    badge_placeholders = ", ".join(f":sid_{index}" for index in range(len(snapshot_ids)))
    params = {"snapshot_version": snapshot_version}
    params.update({f"sid_{index}": value for index, value in enumerate(snapshot_ids)})

    badge_rows = db.execute(
        text(
            "SELECT snapshot_id, badge_name, badge_label, badge_color "
            "FROM alert_candidate_snapshot_badges "
            "WHERE snapshot_version = :snapshot_version "
            f"AND snapshot_id IN ({badge_placeholders})"
        ),
        params,
    ).fetchall()
    badge_map = {}
    for row in badge_rows:
        badge_map.setdefault(row[0], []).append(
            {"name": row[1], "label": row[2], "color": row[3]}
        )

    tag_rows = db.execute(
        text(
            "SELECT snapshot_id, tag_id, tag_name, tag_color "
            "FROM alert_candidate_snapshot_tags "
            "WHERE snapshot_version = :snapshot_version "
            f"AND snapshot_id IN ({badge_placeholders})"
        ),
        params,
    ).fetchall()
    tag_map = {}
    for row in tag_rows:
        tag_map.setdefault(row[0], []).append(
            {"id": row[1], "name": row[2], "color": row[3]}
        )

    for item in items:
        sid = item.get("id")
        item["badges"] = badge_map.get(sid, [])
        item["device_tags"] = tag_map.get(sid, [])
    return items


def _query_items(db, where, params, page, page_size, badges_filter=None, sort_by=None, sort_order=None):
    sort_by_map = {
        "device_id": "a.device_id",
        "first_alert_time": "a.first_alert_time",
        "last_alert_time": "a.last_alert_time",
        "source_ip": "a.source_ip",
        "target": "a.target",
        "port": "a.port",
        "threat_type": "a.threat_type",
        "threat_level": "a.threat_level",
        "std_apt_org": "a.std_apt_org",
        "apt_org": "a.apt_org",
        "alert_count": "a.alert_count",
    }
    order_col = sort_by_map.get(sort_by, "a.first_alert_time")
    direction = "ASC" if str(sort_order or "").lower() == "asc" else "DESC"
    order_clause = f"{order_col} {direction}"

    enabled_badges = set(get_config().get("badges", {}).get("enabled", []))
    requested_badges = set(_csv_values(badges_filter))
    need_cross_day = "cross_day" in enabled_badges or "cross_day" in requested_badges
    need_lateral = "lateral" in enabled_badges or "lateral" in requested_badges
    cross_day_pairs, lateral_ips = _cross_day_and_lateral(
        db,
        where,
        params,
        need_cross_day=need_cross_day,
        need_lateral=need_lateral,
    )

    if badges_filter:
        all_rows = db.execute(
            text(
                f"""
                SELECT a.* FROM alerts a
                WHERE {where}
                ORDER BY {order_clause}
                """
            ),
            params,
        ).fetchall()
        items = _make_items(db, all_rows, cross_day_pairs, lateral_ips, badges_filter, trace_index=_preload_trace_index(db))
        heat_maps, source_ip_maps = _heat_and_source_maps(db, where, params, all_rows)
        for item in items:
            sip_key = (item.get("device_id") or "", item.get("target") or "", item.get("port") or "")
            sip_data = source_ip_maps.get(sip_key, {})
            item["source_ips"] = sip_data.get("source_ips", item.get("source_ip") or "")
            item["source_ip_count"] = sip_data.get("source_ip_count", 1 if item.get("source_ip") else 0)
            item["heat"] = {
                "device_alert_count": heat_maps["device_alert_counts"].get((item.get("device_id"), item.get("target"), item.get("port") or ""), 0),
                "device_target_count": heat_maps["device_target_counts"].get(item.get("device_id"), 0),
                "source_ip_alert_count": heat_maps["source_ip_alert_counts"].get(item.get("source_ip"), 0),
                "target_alert_count": heat_maps["target_alert_counts"].get(item.get("target"), 0),
                "target_device_count": heat_maps["target_device_counts"].get(item.get("target"), 0),
            }
        start = (page - 1) * page_size
        return items[start : start + page_size], len(items)

    total = db.execute(text(f"SELECT COUNT(*) FROM alerts a WHERE {where}"), params).scalar() or 0
    query_params = dict(params)
    query_params["limit"] = page_size
    query_params["offset"] = (page - 1) * page_size
    rows = db.execute(
        text(
            f"""
            SELECT a.* FROM alerts a
            WHERE {where}
            ORDER BY {order_clause}
            LIMIT :limit OFFSET :offset
            """
        ),
        query_params,
    ).fetchall()
    items = _make_items(db, rows, cross_day_pairs, lateral_ips, trace_index=_preload_trace_index(db))
    heat_maps, source_ip_maps = _heat_and_source_maps(db, where, params, rows)
    for item in items:
        sip_key = (item.get("device_id") or "", item.get("target") or "", item.get("port") or "")
        sip_data = source_ip_maps.get(sip_key, {})
        item["source_ips"] = sip_data.get("source_ips", item.get("source_ip") or "")
        item["source_ip_count"] = sip_data.get("source_ip_count", 1 if item.get("source_ip") else 0)
        item["heat"] = {
            "device_alert_count": heat_maps["device_alert_counts"].get((item.get("device_id"), item.get("target"), item.get("port") or ""), 0),
            "device_target_count": heat_maps["device_target_counts"].get(item.get("device_id"), 0),
            "source_ip_alert_count": heat_maps["source_ip_alert_counts"].get(item.get("source_ip"), 0),
            "target_alert_count": heat_maps["target_alert_counts"].get(item.get("target"), 0),
            "target_device_count": heat_maps["target_device_counts"].get(item.get("target"), 0),
        }
    return items, total


def _base_filter_params(
    *,
    date_start=None,
    date_end=None,
    target_type=None,
    device_tags=None,
    exclude_device_tags=None,
    hide_traced=True,
    hide_closed=True,
    keyword=None,
    alert_count_max=None,
):
    where, params = _build_where(
        date_start=date_start,
        date_end=date_end,
        target_type=target_type,
        device_tags=device_tags,
        exclude_device_tags=exclude_device_tags,
        threat_types=None,
        threat_levels=None,
        apt_tiers=None,
        hide_traced=hide_traced,
        hide_closed=hide_closed,
        keyword=keyword,
        alert_count_max=alert_count_max,
    )
    return where, params


def _candidate_scope_meta(snapshot_status=None, message=None, rebuilding=None):
    meta = {
        "platform_scope": {
            "imports_all_sheets": True,
            "imports_original_alert_rows": True,
            "dedupe_policy": "exact_alert_content_with_time",
        },
        "candidate_scope": {
            "default_rules": [rule["id"] for rule in DEFAULT_CANDIDATE_RULES],
            "default_rule_labels": [rule["label"] for rule in DEFAULT_CANDIDATE_RULES],
            "first_screen_goal": "show script-like high-risk candidates before raw full-list review",
            "rule_catalog": [
                {
                    "id": rule["id"],
                    "label": rule["label"],
                    "field": rule["field"],
                }
                for rule in DEFAULT_CANDIDATE_RULES
            ],
            "sort_logic": [
                "candidate priority",
                "candidate score",
                "target device heat",
                "target alert heat",
                "source ip heat",
                "latest alert time",
            ],
        },
        "differences_from_script": [
            "platform imports all sheets and keeps raw row traceability",
            "candidate view is a filtered workbench view, not the full raw alert table",
            "result counts can differ from the old script because platform and script scopes are different",
        ],
    }
    if snapshot_status is not None:
        meta["snapshot_status"] = snapshot_status
    if message:
        meta["message"] = message
    if rebuilding is not None:
        meta["snapshot_rebuilding"] = rebuilding
    return meta


def _candidate_filter_sql():
    return build_candidate_rule_sql(DEFAULT_CANDIDATE_RULES, table_alias="a", prefix="candidate_kw")


def _target_kind_label(kind):
    return {
        "ip": "IP \u89c6\u89d2",
        "domain": "\u57df\u540d\u89c6\u89d2",
        "other": "\u5176\u4ed6 IOC \u89c6\u89d2",
        "unknown": "\u5f85\u786e\u8ba4\u89c6\u89d2",
    }.get(kind, "\u5176\u4ed6 IOC \u89c6\u89d2")


def _heat_summary(heat):
    return {
        "device": f"\u8bbe\u5907 {heat['device_alert_count']} \u6761",
        "source_ip": f"\u6e90 IP {heat['source_ip_alert_count']} \u6761",
        "target": f"\u76ee\u6807 {heat['target_alert_count']} \u6761",
        "target_devices": f"{heat['target_device_count']} \u53f0\u8bbe\u5907",
    }


SQL_BASE_CANDIDATE_SCORE = """\
COALESCE(
  (CASE WHEN LOWER(COALESCE(a.threat_type, '')) LIKE '%apt%' THEN 34 ELSE 0 END)
+ (CASE WHEN LOWER(COALESCE(a.threat_type, '')) LIKE '%远控%' OR LOWER(COALESCE(a.threat_type, '')) LIKE '%remote%' THEN 30 ELSE 0 END)
+ (CASE WHEN COALESCE(a.std_apt_org, '') != '' THEN 26 ELSE 0 END)
+ (CASE WHEN COALESCE(a.apt_org, '') != '' THEN 22 ELSE 0 END)
+ (CASE WHEN LOWER(COALESCE(a.intel_tags, '')) LIKE '%apt%' OR LOWER(COALESCE(a.intel_tags, '')) LIKE '%c2%' OR LOWER(COALESCE(a.intel_tags, '')) LIKE '%远控%' OR LOWER(COALESCE(a.intel_tags, '')) LIKE '%remote%' THEN 18 ELSE 0 END)
+ (CASE WHEN LOWER(COALESCE(a.threat_level, '')) IN ('critical', 'high', '高') THEN 18 WHEN LOWER(COALESCE(a.threat_level, '')) IN ('medium', '中') THEN 8 WHEN LOWER(COALESCE(a.threat_level, '')) IN ('low', '低') THEN 3 ELSE 0 END)
+ (CASE WHEN LOWER(COALESCE(a.apt_org_tier, '')) IN ('s', 's级', 'a', 'a级', 'high', '高') THEN 16 WHEN LOWER(COALESCE(a.apt_org_tier, '')) IN ('b', 'b级', 'medium', '中') THEN 10 WHEN COALESCE(a.apt_org_tier, '') != '' THEN 6 ELSE 0 END)
, 0)"""

SQL_CANDIDATE_SORTS = {
    "device_id": "COALESCE(a.device_id, '') COLLATE NOCASE",
    "source_ip": "COALESCE(a.source_ip, '') COLLATE NOCASE",
    "target": "COALESCE(a.target, '') COLLATE NOCASE",
    "port": "COALESCE(a.port, '') COLLATE NOCASE",
    "threat_type": "COALESCE(a.threat_type, '') COLLATE NOCASE",
    "std_apt_org": "COALESCE(a.std_apt_org, '') COLLATE NOCASE",
    "analysis_status": "COALESCE(a.analysis_status, '') COLLATE NOCASE",
    "is_focused": "COALESCE(a.is_focused, 0)",
    "first_alert_time": "a.first_alert_time",
    "last_alert_time": "a.last_alert_time",
    "alert_count": "COALESCE(a.alert_count, 0)",
    "candidate_score": SQL_BASE_CANDIDATE_SCORE,
}

SORT_FIELD_ALIASES = {
    "score": "candidate_score",
    "candidate_score": "candidate_score",
    "heat": "target_alert_count",
    "heat.target_alert_count": "target_alert_count",
    "heat.target_device_count": "target_device_count",
    "heat.device_alert_count": "device_alert_count",
    "device_alert_count": "device_alert_count",
    "heat.device_target_count": "device_target_count",
    "device_target_count": "device_target_count",
    "trace_status": "trace_status",
}

TRACE_SORT_RANK = {"none": 0, "expired": 1, "active": 2}


def _normalize_candidate_sort(sort_by=None, sort_order=None):
    if not isinstance(sort_by, str):
        sort_by = ""
    if not isinstance(sort_order, str):
        sort_order = ""
    normalized = (sort_by or "").strip()
    normalized = SORT_FIELD_ALIASES.get(normalized, normalized)
    direction = "ASC" if str(sort_order or "").lower() == "asc" else "DESC"
    return normalized, direction


def _candidate_sort_value(item, sort_field):
    if sort_field == "candidate_score":
        return item.get("candidate_score") or 0
    if sort_field in {"device_alert_count", "device_target_count", "target_alert_count", "target_device_count"}:
        return (item.get("heat") or {}).get(sort_field) or 0
    if sort_field == "trace_status":
        return TRACE_SORT_RANK.get(item.get("trace_status"), 0)
    if sort_field == "is_focused":
        return 1 if item.get("is_focused") else 0
    if sort_field in {"device_id", "source_ip", "target", "port", "threat_type", "std_apt_org", "analysis_status"}:
        return str(item.get(sort_field) or "").lower()
    if sort_field in {"first_alert_time", "last_alert_time"}:
        return str(item.get(sort_field) or "")
    if sort_field == "alert_count":
        return item.get("alert_count") or 0
    if sort_field == "source_ip_count":
        return item.get("source_ip_count") or 0
    return None


def _sort_candidate_items(items, sort_field=None, sort_direction="DESC"):
    reverse = sort_direction != "ASC"
    if sort_field:
        items.sort(
            key=lambda item: (
                _candidate_sort_value(item, sort_field),
                item.get("sort_signals", {}).get("priority_rank") or 0,
                item.get("candidate_score") or 0,
                str(item.get("last_alert_time") or ""),
            ),
            reverse=reverse,
        )
        return

    items.sort(
        key=lambda item: (
            item.get("sort_signals", {}).get("priority_rank") or 0,
            item.get("candidate_score") or 0,
            item.get("heat", {}).get("target_device_count") or 0,
            item.get("heat", {}).get("target_alert_count") or 0,
            item.get("heat", {}).get("source_ip_alert_count") or 0,
            item.get("alert_count") or 0,
            str(item.get("last_alert_time") or ""),
        ),
        reverse=True,
    )


def _get_sorted_candidate_view(cache_entry, sort_field=None, sort_direction="DESC"):
    normalized_sort_field = sort_field or "candidate_score"
    normalized_sort_direction = sort_direction or "DESC"
    sort_key = f"{normalized_sort_field}:{normalized_sort_direction}"
    sorted_views = cache_entry.setdefault("sorted_views", {})
    if sort_key in sorted_views:
        return sorted_views[sort_key]

    sorted_items = list(cache_entry["items"])
    _sort_candidate_items(
        sorted_items,
        sort_field=normalized_sort_field,
        sort_direction=normalized_sort_direction,
    )
    sorted_views[sort_key] = sorted_items
    return sorted_items


def _heat_and_source_maps(db, base_where, base_params, rows):
    """Single consolidated query: replaces _heat_maps_for_rows + _source_ip_maps_for_rows.
    5+1 separate scans → 1 scan. Returns heat maps and source_ip maps."""
    device_alert_counts = {}
    device_target_counts = {}
    source_ip_alert_counts = {}
    target_alert_counts = {}
    target_device_counts = {}
    source_ip_map = {}

    # Build lookup keys for source_ip_map (only need these, not all)
    needed_keys = {
        (row._mapping.get("device_id") or "", row._mapping.get("target") or "", row._mapping.get("port") or "")
        for row in rows
    }

    # Single pass: all aggregates + source_ip aggregation
    agg_rows = db.execute(
        text(
            f"""
            SELECT a.device_id, a.target, COALESCE(a.port, '') as port,
                   a.source_ip,
                   COUNT(*) AS alert_count,
                   GROUP_CONCAT(DISTINCT a.source_ip) as source_ips,
                   COUNT(DISTINCT a.source_ip) as source_ip_count
            FROM alerts a
            WHERE {base_where}
            GROUP BY a.device_id, a.target, COALESCE(a.port, '')
            """
        ),
        base_params,
    ).fetchall()

    for row in agg_rows:
        device_id, target, port, source_ip, count, raw_ips, ip_count = (
            row[0], row[1], row[2], row[3], row[4], row[5], row[6]
        )
        device_alert_counts[(device_id, target, port)] = count
        device_target_counts[device_id] = device_target_counts.get(device_id, 0) + 1
        target_alert_counts[target] = target_alert_counts.get(target, 0) + count
        source_ip_alert_counts[source_ip] = source_ip_alert_counts.get(source_ip, 0) + count if source_ip else 0

        key = (device_id, target, port)
        if key in needed_keys:
            source_ip_map[key] = {
                "source_ips": raw_ips.replace(",", " | ") if raw_ips else "",
                "source_ip_count": ip_count or 0,
            }

    # Compute target_device_counts
    target_devices_map = {}
    for row in agg_rows:
        target_devices_map.setdefault(row[1], set()).add(row[0])
    for target, devs in target_devices_map.items():
        target_device_counts[target] = len(devs)

    return {
        "device_alert_counts": device_alert_counts,
        "device_target_counts": device_target_counts,
        "source_ip_alert_counts": source_ip_alert_counts,
        "target_alert_counts": target_alert_counts,
        "target_device_counts": target_device_counts,
    }, source_ip_map


def _source_ip_maps_for_rows(db, base_where, base_params, rows):
    """Collect all distinct source IPs per (device_id, target, port) group.

    Uses a simple GROUP BY query without per-key OR clauses to avoid SQLite's
    "expression tree too large" error when decorating thousands of rows.
    """
    keys = sorted({(
        row._mapping.get("device_id") or "",
        row._mapping.get("target") or "",
        row._mapping.get("port") or "",
    ) for row in rows})
    source_ip_map = {}
    if not keys:
        return source_ip_map

    # Simple GROUP BY over all alerts in the date range. No OR clauses.
    result_rows = db.execute(
        text(
            f"""
            SELECT a.device_id, a.target, COALESCE(a.port, '') as port,
                   GROUP_CONCAT(DISTINCT a.source_ip) as source_ips,
                   COUNT(DISTINCT a.source_ip) as source_ip_count
            FROM alerts a
            WHERE {base_where}
            GROUP BY a.device_id, a.target, COALESCE(a.port, '')
            """
        ),
        base_params,
    ).fetchall()

    # Build lookup for only the keys we need
    key_set = set(keys)
    for row in result_rows:
        k = (row[0], row[1], row[2])
        if k not in key_set:
            continue
        raw_ips = row[3] or ""
        source_ip_map[k] = {
            "source_ips": raw_ips.replace(",", " | ") if raw_ips else "",
            "source_ip_count": row[4] or 0,
        }
    return source_ip_map


def _decorate_candidate_items(db, base_where, base_params, rows, badges_filter=None, target_kind=None, sort_field=None, sort_direction="DESC"):
    enabled_badges = set(get_config().get("badges", {}).get("enabled", []))
    requested_badges = set(_csv_values(badges_filter))
    need_cross_day = "cross_day" in enabled_badges or "cross_day" in requested_badges
    need_lateral = "lateral" in enabled_badges or "lateral" in requested_badges
    cross_day_pairs, lateral_ips = _cross_day_and_lateral(
        db,
        base_where,
        base_params,
        need_cross_day=need_cross_day,
        need_lateral=need_lateral,
    )
    items = _make_items(db, rows, cross_day_pairs, lateral_ips, badges_filter, trace_index=_preload_trace_index(db))
    heat_maps, source_ip_maps = _heat_and_source_maps(db, base_where, base_params, rows)

    decorated = []
    for item in items:
        item_target_kind = classify_target_kind(item.get("target"), item.get("target_type"))
        if target_kind and target_kind != "all" and item_target_kind != target_kind:
            continue

        sip_key = (item.get("device_id") or "", item.get("target") or "", item.get("port") or "")
        sip_data = source_ip_maps.get(sip_key, {})
        item["source_ips"] = sip_data.get("source_ips", item.get("source_ip") or "")
        item["source_ip_count"] = sip_data.get("source_ip_count", 1 if item.get("source_ip") else 0)

        matches = detect_candidate_matches(item)
        heat = {
            "device_alert_count": heat_maps["device_alert_counts"].get((item.get("device_id"), item.get("target"), item.get("port") or ""), 0),
            "device_target_count": heat_maps["device_target_counts"].get(item.get("device_id"), 0),
            "source_ip_alert_count": heat_maps["source_ip_alert_counts"].get(item.get("source_ip"), 0),
            "target_alert_count": heat_maps["target_alert_counts"].get(item.get("target"), 0),
            "target_device_count": heat_maps["target_device_counts"].get(item.get("target"), 0),
        }
        trace_info = item.get("traced")
        event_info = item.get("event")
        device_tags = item.get("device_tags") or []

        item["candidate_rule_ids"] = [rule["id"] for rule in matches]
        item["candidate_reasons"] = build_candidate_reason_labels(
            item,
            matches,
            heat=heat,
            trace_info=trace_info,
            event_info=event_info,
            device_tags=device_tags,
        )
        item["candidate_score"] = compute_candidate_score(
            item,
            matches,
            heat,
            trace_info=trace_info,
            event_info=event_info,
            device_tags=device_tags,
        )
        priority = classify_candidate_priority(item["candidate_score"])
        item["target_kind"] = item_target_kind
        item["target_kind_label"] = _target_kind_label(item_target_kind)
        item["script_bucket"] = item_target_kind if item_target_kind in {"ip", "domain"} else "other"
        item["candidate_priority"] = priority["id"]
        item["candidate_priority_label"] = priority["label"]
        item["heat"] = heat
        item["heat_summary"] = _heat_summary(heat)
        item["device_note_summary"] = " | ".join(tag["name"] for tag in device_tags)
        item["trace_status"] = (
            "active"
            if trace_info and trace_info.get("active")
            else "expired"
            if trace_info
            else "none"
        )
        item["ioc_note"] = trace_info.get("note") if trace_info else None
        item["trace_status_label"] = (
            "\u8ffd\u8e2a TTL \u5185"
            if item["trace_status"] == "active"
            else "\u5386\u53f2\u8ffd\u8e2a"
            if item["trace_status"] == "expired"
            else "\u672a\u8ffd\u8e2a"
        )
        item["event_status"] = event_info.get("status") if event_info else None
        item["candidate_focus"] = (
            f"{item['target_kind_label']} | {item['heat_summary']['target']} | {item['heat_summary']['target_devices']}"
        )
        item["candidate_summary"] = " | ".join(item["candidate_reasons"][:4])
        item["sort_signals"] = {
            "priority_rank": priority["rank"],
            "rule_hits": len(matches),
            "target_device_count": heat["target_device_count"],
            "target_alert_count": heat["target_alert_count"],
            "source_ip_alert_count": heat["source_ip_alert_count"],
            "trace_status": item["trace_status"],
            "event_status": item["event_status"],
        }
        decorated.append(item)

    _sort_candidate_items(decorated, sort_field=sort_field, sort_direction=sort_direction)
    return decorated


HEAT_SORT_JOINS = {
    "target_alert_count": (
        "LEFT JOIN (SELECT target, COUNT(*) AS cnt FROM alerts GROUP BY target) ht ON a.target = ht.target",
        "COALESCE(ht.cnt, 0)",
    ),
    "target_device_count": (
        "LEFT JOIN (SELECT target, COUNT(DISTINCT device_id) AS cnt FROM alerts GROUP BY target) htd ON a.target = htd.target",
        "COALESCE(htd.cnt, 0)",
    ),
    "device_alert_count": (
        "LEFT JOIN (SELECT device_id, target, COALESCE(port, '') as port, COUNT(*) AS cnt FROM alerts GROUP BY device_id, target, COALESCE(port, '')) hd ON a.device_id = hd.device_id AND a.target = hd.target AND COALESCE(a.port, '') = hd.port",
        "COALESCE(hd.cnt, 0)",
    ),
    "device_target_count": (
        "LEFT JOIN (SELECT device_id, COUNT(DISTINCT target) AS cnt FROM alerts GROUP BY device_id) hdt ON a.device_id = hdt.device_id",
        "COALESCE(hdt.cnt, 0)",
    ),
}

TRACE_STATUS_SORT_EXPR = """\
CASE
  WHEN EXISTS (SELECT 1 FROM traced_targets tt WHERE tt.target = a.target AND COALESCE(tt.port, '') IN ('', COALESCE(a.port, '')) AND (tt.traced_at IS NULL OR tt.traced_at >= datetime('now', '-' || CAST(:trace_ttl_days AS TEXT) || ' days'))) THEN 2
  WHEN EXISTS (SELECT 1 FROM traced_targets tt WHERE tt.target = a.target AND COALESCE(tt.port, '') IN ('', COALESCE(a.port, ''))) THEN 1
  ELSE 0
END"""


def _query_all_candidate_items(
    db,
    base_where,
    base_params,
    badges_filter=None,
    target_kind=None,
):
    """Fetch ALL candidate items (no SQL LIMIT), fully decorated.

    Used by the cache layer: one expensive fetch, then re-sort/page in Python.
    No candidate rule filter — all alerts are shown, scored and sorted.
    """
    where = base_where
    params = dict(base_params)

    cfg = get_config()
    ttl_days = cfg.get("rules", {}).get("trace_ttl_days", 30)

    _DEDUP_PARTITION = (
        "ROW_NUMBER() OVER ("
        "PARTITION BY a.device_id, a.target, COALESCE(a.port, '') "
        "ORDER BY a.alert_count DESC, a.last_alert_time DESC, a.id DESC"
        ") AS _rn"
    )
    _DEDUP_WRAP = (
        "SELECT sub.* FROM ("
        "SELECT a.*, {dedup_rn} "
        "FROM alerts a "
        "WHERE {where}"
        ") sub"
        " WHERE sub._rn = 1"
    ).format(dedup_rn=_DEDUP_PARTITION, where=where)

    # Fetch ALL deduped rows (no LIMIT)
    rows = db.execute(
        text(f"{_DEDUP_WRAP} ORDER BY sub.first_alert_time DESC"),
        params,
    ).fetchall()

    # Full decoration
    items = _decorate_candidate_items(
        db,
        base_where,
        base_params,
        rows,
        badges_filter=badges_filter,
        target_kind=target_kind,
        sort_field=None,
        sort_direction="DESC",
    )
    return items, len(items)


def _query_candidate_items(
    db,
    base_where,
    base_params,
    page,
    page_size,
    badges_filter=None,
    target_kind=None,
    sort_by=None,
    sort_order=None,
):
    where = base_where
    params = dict(base_params)

    sort_field, sort_direction = _normalize_candidate_sort(sort_by, sort_order)
    # Default to candidate_score DESC to ensure SQL-level paging is always used
    if not sort_field:
        sort_field = "candidate_score"
        sort_direction = "DESC"
    cfg = get_config()
    ttl_days = cfg.get("rules", {}).get("trace_ttl_days", 30)

    # Determine SQL sort expression
    extra_joins = ""
    extra_select = ""
    order_expr = None
    if sort_field in SQL_CANDIDATE_SORTS:
        order_expr = SQL_CANDIDATE_SORTS[sort_field]
    elif sort_field in HEAT_SORT_JOINS:
        join_clause, sort_expr = HEAT_SORT_JOINS[sort_field]
        extra_joins = " " + join_clause
        extra_select = f", {sort_expr} AS _sort_val"
        order_expr = "sub._sort_val"
    elif sort_field == "trace_status":
        order_expr = TRACE_STATUS_SORT_EXPR
        params["trace_ttl_days"] = ttl_days

    # Re-alias sort expression from inner 'a.' to outer 'sub.' for dedup wrapper
    if order_expr:
        import re as _re
        order_expr = _re.sub(r'\ba\.', 'sub.', order_expr)

    # Dedup: each (device_id, target, port) appears at most once in candidates,
    # keeping the row with the highest alert_count, then latest last_alert_time.
    _DEDUP_PARTITION = (
        "ROW_NUMBER() OVER ("
        "PARTITION BY a.device_id, a.target, COALESCE(a.port, '') "
        "ORDER BY a.alert_count DESC, a.last_alert_time DESC, a.id DESC"
        ") AS _rn"
    )
    _DEDUP_WRAP = (
        "SELECT sub.* FROM ("
        "SELECT a.*{{extra_select}}, {dedup_rn} "
        "FROM alerts a{{extra_joins}} "
        "WHERE {{where}}"
        ") sub"
        " WHERE sub._rn = 1"
    ).format(dedup_rn=_DEDUP_PARTITION)

    can_page_before_decorating = (
        order_expr is not None
        and not badges_filter
        and (not target_kind or target_kind == "all")
    )

    if can_page_before_decorating:
        total = db.execute(
            text(
                f"SELECT COUNT(*) FROM ("
                f"SELECT 1 FROM alerts a WHERE {where} "
                f"GROUP BY a.device_id, a.target, COALESCE(a.port, ''))"
            ),
            params,
        ).scalar() or 0
        query_params = dict(params)
        query_params["limit"] = page_size
        query_params["offset"] = (page - 1) * page_size
        order_clause = f"{order_expr} {sort_direction}"
        dedup_sql = _DEDUP_WRAP.format(extra_joins=extra_joins, extra_select=extra_select, where=where)
        rows = db.execute(
            text(
                f"""
                {dedup_sql}
                ORDER BY {order_clause}, sub.first_alert_time DESC, sub.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            query_params,
        ).fetchall()
        items = _decorate_candidate_items(
            db,
            base_where,
            base_params,
            rows,
            badges_filter=badges_filter,
            target_kind=target_kind,
            sort_field=sort_field,
            sort_direction=sort_direction,
        )
        return items, total

    # Fallback: fetch all deduped rows and sort in Python (for badge-filtered or target_kind-filtered with computed sort)
    dedup_sql = _DEDUP_WRAP.format(extra_joins=extra_joins, extra_select=extra_select, where=where)
    order_prefix = f"{order_expr} {sort_direction}, " if order_expr else ""
    rows = db.execute(
        text(
            f"""
            {dedup_sql}
            ORDER BY {order_prefix}sub.first_alert_time DESC
            """
        ),
        params,
    ).fetchall()
    items = _decorate_candidate_items(
        db,
        base_where,
        base_params,
        rows,
        badges_filter=badges_filter,
        target_kind=target_kind,
        sort_field=sort_field,
        sort_direction=sort_direction,
    )
    if sort_field:
        _sort_candidate_items(items, sort_field, sort_direction)
    start = (page - 1) * page_size
    return items[start : start + page_size], len(items)


@router.get("/options")
def get_alert_options(
    date_start: str = Query(None),
    date_end: str = Query(None),
    target_type: str = Query(None),
    exclude_device_tags: str = Query(None),
    hide_traced: Optional[bool] = Query(None),
    hide_closed: Optional[bool] = Query(None),
    keyword: str = Query(None),
    alert_count_max: int = Query(None),
    db=Depends(get_db),
):
    hide_traced, hide_closed = _resolve_hide_defaults(hide_traced, hide_closed)
    where, params = _base_filter_params(
        date_start=date_start,
        date_end=date_end,
        target_type=target_type,
        exclude_device_tags=exclude_device_tags,
        hide_traced=hide_traced,
        hide_closed=hide_closed,
        keyword=keyword,
        alert_count_max=alert_count_max,
    )

    threat_rows = db.execute(
        text(
            f"""
            SELECT a.threat_type
            FROM alerts a
            WHERE {where} AND COALESCE(a.threat_type, '') != ''
            ORDER BY a.last_alert_time DESC
            LIMIT 5000
            """
        ),
        params,
    ).fetchall()
    threat_types = []
    seen_threat_types = set()
    for row in threat_rows:
        for item in _split_multi_values(row[0]):
            lowered = item.lower()
            if lowered in seen_threat_types:
                continue
            seen_threat_types.add(lowered)
            threat_types.append(item)

    target_type_rows = db.execute(
        text(
            f"""
            SELECT DISTINCT a.target_type
            FROM alerts a
            WHERE {where} AND COALESCE(a.target_type, '') != ''
            ORDER BY a.target_type
            """
        ),
        params,
    ).fetchall()
    target_types = [row[0] for row in target_type_rows]

    threat_level_rows = db.execute(
        text(
            f"""
            SELECT DISTINCT a.threat_level
            FROM alerts a
            WHERE {where} AND COALESCE(a.threat_level, '') != ''
            ORDER BY a.threat_level
            """
        ),
        params,
    ).fetchall()
    threat_levels = [row[0] for row in threat_level_rows]

    tag_rows = db.execute(
        text(
            f"""
            SELECT DISTINCT t.id, t.name, t.color
            FROM alerts a
            JOIN device_tags dt ON dt.device_id = a.device_id
            JOIN tags t ON t.id = dt.tag_id
            WHERE {where}
            ORDER BY t.created_at DESC, t.id DESC
            """
        ),
        params,
    ).fetchall()
    device_tags = [{"id": row[0], "name": row[1], "color": row[2]} for row in tag_rows]

    return {
        "threat_types": threat_types,
        "target_types": target_types,
        "threat_levels": threat_levels,
        "device_tags": device_tags,
    }


@router.get("")
def query_alerts(
    date_start: str = Query(None),
    date_end: str = Query(None),
    target_type: str = Query(None),
    device_tags: str = Query(None),
    exclude_device_tags: str = Query(None),
    threat_types: str = Query(None),
    threat_levels: str = Query(None),
    apt_tiers: str = Query(None),
    hide_traced: Optional[bool] = Query(None),
    hide_closed: Optional[bool] = Query(None),
    keyword: str = Query(None),
    alert_count_max: int = Query(None),
    badges_filter: str = Query(None),
    sort_by: str = Query(None),
    sort_order: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100000),
    db=Depends(get_db),
):
    hide_traced, hide_closed = _resolve_hide_defaults(hide_traced, hide_closed)
    where, params = _build_where(
        date_start=date_start,
        date_end=date_end,
        target_type=target_type,
        device_tags=device_tags,
        exclude_device_tags=exclude_device_tags,
        threat_types=threat_types,
        threat_levels=threat_levels,
        apt_tiers=apt_tiers,
        hide_traced=hide_traced,
        hide_closed=hide_closed,
        keyword=keyword,
        alert_count_max=alert_count_max,
    )
    items, total = _query_items(db, where, params, page, page_size, badges_filter, sort_by=sort_by, sort_order=sort_order)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@candidate_router.get("")
def query_alert_candidates(
    date_start: str = Query(None),
    date_end: str = Query(None),
    target_type: str = Query(None),
    device_tags: str = Query(None),
    exclude_device_tags: str = Query(None),
    threat_types: str = Query(None),
    threat_levels: str = Query(None),
    apt_tiers: str = Query(None),
    hide_traced: Optional[bool] = Query(None),
    hide_closed: Optional[bool] = Query(None),
    keyword: str = Query(None),
    alert_count_max: int = Query(None),
    badges_filter: str = Query(None),
    target_kind: str = Query("all"),
    sort_by: str = Query(None),
    sort_order: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100000),
    db=Depends(get_db),
):
    hide_traced, hide_closed = _resolve_hide_defaults(hide_traced, hide_closed)
    sort_field, sort_direction = _normalize_candidate_sort(sort_by, sort_order)
    if not sort_field:
        sort_field = "candidate_score"
        sort_direction = "DESC"
    meta_row = get_snapshot_meta(db, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES)
    active_version = get_active_snapshot_version(db, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES)
    if not active_version:
        if (meta_row or {}).get("status") != SNAPSHOT_STATUS_BUILDING:
            try:
                rebuild_candidate_snapshots_async()
            except Exception:
                pass
        return {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": page_size,
            "meta": _candidate_scope_meta(
                snapshot_status=SNAPSHOT_STATUS_BUILDING,
                message="候选快照正在构建中，请稍候...",
            ),
            "filter_options": _snapshot_empty_filter_options(),
        }

    conditions = ["s.snapshot_version = :snapshot_version"]
    params = {"snapshot_version": active_version}

    if date_start:
        conditions.append("COALESCE(s.first_alert_time, '') >= :date_start")
        params["date_start"] = f"{date_start} 00:00:00"
    if date_end:
        conditions.append("COALESCE(s.first_alert_time, '') <= :date_end_bound")
        params["date_end_bound"] = f"{date_end} 23:59:59"
    if target_type:
        conditions.append("s.target_type = :target_type")
        params["target_type"] = target_type
    if target_kind and target_kind != "all":
        conditions.append("s.target_kind = :target_kind")
        params["target_kind"] = target_kind

    selected_threat_types = _csv_values(threat_types)
    if selected_threat_types:
        clauses = []
        for index, item in enumerate(selected_threat_types):
            key = f"tt_{index}"
            clauses.append(f"COALESCE(s.threat_type, '') LIKE :{key}")
            params[key] = f"%{item}%"
        conditions.append("(" + " OR ".join(clauses) + ")")

    levels = _csv_values(threat_levels)
    if levels:
        placeholders = ", ".join(f":tl_{index}" for index in range(len(levels)))
        conditions.append(f"s.threat_level IN ({placeholders})")
        for index, level in enumerate(levels):
            params[f"tl_{index}"] = level

    tiers = _csv_values(apt_tiers)
    if tiers:
        placeholders = ", ".join(f":at_{index}" for index in range(len(tiers)))
        conditions.append(f"s.apt_org_tier IN ({placeholders})")
        for index, tier in enumerate(tiers):
            params[f"at_{index}"] = tier

    tag_ids = _csv_values(device_tags)
    if tag_ids:
        placeholders = ", ".join(f":tag_{index}" for index in range(len(tag_ids)))
        conditions.append(
            "EXISTS (SELECT 1 FROM alert_candidate_snapshot_tags st "
            f"WHERE st.snapshot_id = s.id AND st.snapshot_version = s.snapshot_version AND st.tag_id IN ({placeholders}))"
        )
        for index, tag_id in enumerate(tag_ids):
            params[f"tag_{index}"] = int(tag_id)

    exclude_tag_ids = _csv_values(exclude_device_tags)
    if exclude_tag_ids:
        placeholders = ", ".join(f":et_{index}" for index in range(len(exclude_tag_ids)))
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM alert_candidate_snapshot_tags st "
            f"WHERE st.snapshot_id = s.id AND st.snapshot_version = s.snapshot_version AND st.tag_id IN ({placeholders}))"
        )
        for index, tag_id in enumerate(exclude_tag_ids):
            params[f"et_{index}"] = int(tag_id)

    if hide_traced:
        conditions.append("COALESCE(s.trace_status, 'none') != 'active'")
    if hide_closed:
        conditions.append("(s.event_status IS NULL OR s.event_status != 'closed')")
    if alert_count_max is not None:
        conditions.append("COALESCE(s.alert_count, 0) <= :alert_count_max")
        params["alert_count_max"] = alert_count_max
    if keyword:
        params["kw"] = f"%{keyword}%"
        conditions.append(
            "(COALESCE(s.device_id, '') LIKE :kw OR COALESCE(s.source_ip, '') LIKE :kw "
            "OR COALESCE(s.target, '') LIKE :kw OR COALESCE(s.threat_type, '') LIKE :kw "
            "OR COALESCE(s.apt_org, '') LIKE :kw OR COALESCE(s.std_apt_org, '') LIKE :kw)"
        )

    badge_filters = _csv_values(badges_filter)
    for index, badge_name in enumerate(badge_filters):
        key = f"badge_{index}"
        params[key] = badge_name
        conditions.append(
            "EXISTS (SELECT 1 FROM alert_candidate_snapshot_badges sb "
            f"WHERE sb.snapshot_id = s.id AND sb.snapshot_version = s.snapshot_version AND sb.badge_name = :{key})"
        )

    where = " AND ".join(conditions) if conditions else "1=1"
    total = db.execute(
        text(f"SELECT COUNT(*) FROM alert_candidate_snapshots s WHERE {where}"),
        params,
    ).scalar() or 0

    query_params = dict(params)
    query_params["limit"] = page_size
    query_params["offset"] = (page - 1) * page_size
    rows = db.execute(
        text(
            f"SELECT s.* FROM alert_candidate_snapshots s WHERE {where} "
            f"ORDER BY {_snapshot_sort_clause(sort_field, sort_direction)} LIMIT :limit OFFSET :offset"
        ),
        query_params,
    ).fetchall()

    items = [_deserialize_snapshot_row(dict(row._mapping)) for row in rows]
    items = _attach_snapshot_relations(db, items, active_version)
    filter_options = _build_snapshot_filter_options(db, where, params)
    meta_status = "ready" if active_version else (meta_row or {}).get("status", "ready")
    rebuilding = (meta_row or {}).get("status") == SNAPSHOT_STATUS_BUILDING and bool(active_version)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "meta": _candidate_scope_meta(snapshot_status=meta_status, rebuilding=rebuilding),
        "filter_options": filter_options,
    }


@router.get("/stats")
def get_stats(db=Depends(get_db)):
    today = date.today().isoformat()
    return {
        "today_alerts": db.execute(
            text("SELECT COUNT(*) FROM alerts WHERE DATE(first_alert_time) = :today"),
            {"today": today},
        ).scalar()
        or 0,
        "total_alerts": db.execute(text("SELECT COUNT(*) FROM alerts")).scalar() or 0,
        "mined_events": db.execute(
            text("SELECT COUNT(*) FROM mined_events WHERE status != 'closed'")
        ).scalar()
        or 0,
        "pending_review": db.execute(
            text(
                "SELECT COUNT(DISTINCT device_id) FROM mined_event_devices WHERE event_id IN "
                "(SELECT id FROM mined_events WHERE status = 'active')"
            )
        ).scalar()
        or 0,
    }


@router.get("/{alert_id}")
def get_alert(alert_id: int, db=Depends(get_db)):
    row = db.execute(text("SELECT * FROM alerts WHERE id = :id"), {"id": alert_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    item = dict(row._mapping)
    _stringify_datetimes(item)
    return item


@router.patch("/{alert_id}/annotation")
def annotate_alert(alert_id: int, data: dict, db=Depends(get_db)):
    row = db.execute(text("SELECT id FROM alerts WHERE id = :id"), {"id": alert_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    updates = []
    params = {"id": alert_id}
    if "analysis_status" in data:
        updates.append("analysis_status = :analysis_status")
        params["analysis_status"] = data["analysis_status"]
    if "is_focused" in data:
        updates.append("is_focused = :is_focused")
        params["is_focused"] = 1 if data["is_focused"] else 0
    if updates:
        db.execute(text(f"UPDATE alerts SET {', '.join(updates)} WHERE id = :id"), params)
        db.commit()
    return {"ok": True}


@router.post("/export")
def export_alerts(
    date_start: str = Query(None),
    date_end: str = Query(None),
    target_type: str = Query(None),
    device_tags: str = Query(None),
    exclude_device_tags: str = Query(None),
    threat_types: str = Query(None),
    threat_levels: str = Query(None),
    apt_tiers: str = Query(None),
    hide_traced: Optional[bool] = Query(None),
    hide_closed: Optional[bool] = Query(None),
    keyword: str = Query(None),
    alert_count_max: int = Query(None),
    badges_filter: str = Query(None),
    db=Depends(get_db),
):
    hide_traced, hide_closed = _resolve_hide_defaults(hide_traced, hide_closed)
    where, params = _build_where(
        date_start=date_start,
        date_end=date_end,
        target_type=target_type,
        device_tags=device_tags,
        exclude_device_tags=exclude_device_tags,
        threat_types=threat_types,
        threat_levels=threat_levels,
        apt_tiers=apt_tiers,
        hide_traced=hide_traced,
        hide_closed=hide_closed,
        keyword=keyword,
        alert_count_max=alert_count_max,
    )
    items, _ = _query_items(db, where, params, 1, 100000, badges_filter)
    dataframe = pd.DataFrame(items)
    if dataframe.empty:
        raise HTTPException(status_code=404, detail="No data to export")

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="alerts")
    buffer.seek(0)

    filename = f"alerts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
