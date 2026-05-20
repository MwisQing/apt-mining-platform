import json
import threading
import uuid
from datetime import datetime

from sqlalchemy import text

from backend.services import _build_trace_index, compute_badges
from backend.services.alert_workbench import (
    DEFAULT_CANDIDATE_RULES,
    classify_candidate_priority,
    compute_candidate_score,
    detect_candidate_matches,
    split_multi_values,
)
from backend.utils import get_config

SNAPSHOT_TYPE_ALERT_CANDIDATES = "alert_candidates"
SNAPSHOT_STATUS_IDLE = "idle"
SNAPSHOT_STATUS_BUILDING = "building"
SNAPSHOT_STATUS_READY = "ready"
SNAPSHOT_STATUS_ERROR = "error"

_snapshot_build_lock = threading.Lock()

# Score mapping for rule IDs used in incremental recomputation
RULE_SCORE_MAP = {
    "threat_type_apt": 34,
    "threat_type_remote_control": 30,
    "std_apt_org_present": 26,
    "apt_org_present": 22,
    "intel_tags_c2_remote": 18,
}

_UNSET = object()  # Sentinel for "don't update this field"


# ---------------------------------------------------------------------------
# Snapshot meta helpers (existing)
# ---------------------------------------------------------------------------

def ensure_snapshot_meta_row(db, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES):
    existing = db.execute(
        text("SELECT snapshot_type FROM snapshot_build_meta WHERE snapshot_type = :snapshot_type"),
        {"snapshot_type": snapshot_type},
    ).fetchone()
    if existing:
        return
    db.execute(
        text(
            "INSERT INTO snapshot_build_meta (snapshot_type, status) "
            "VALUES (:snapshot_type, :status)"
        ),
        {"snapshot_type": snapshot_type, "status": SNAPSHOT_STATUS_IDLE},
    )
    db.commit()


def get_snapshot_meta(db, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES):
    ensure_snapshot_meta_row(db, snapshot_type=snapshot_type)
    row = db.execute(
        text("SELECT * FROM snapshot_build_meta WHERE snapshot_type = :snapshot_type"),
        {"snapshot_type": snapshot_type},
    ).fetchone()
    return dict(row._mapping) if row else None


def get_active_snapshot_version(db, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES):
    row = db.execute(
        text("SELECT active_version FROM snapshot_build_meta WHERE snapshot_type = :snapshot_type"),
        {"snapshot_type": snapshot_type},
    ).fetchone()
    return row[0] if row and row[0] else None


def set_snapshot_building(db, version, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES):
    ensure_snapshot_meta_row(db, snapshot_type=snapshot_type)
    db.execute(
        text(
            "UPDATE snapshot_build_meta SET "
            "building_version = :version, status = :status, "
            "last_build_started_at = :started_at, last_error = NULL "
            "WHERE snapshot_type = :snapshot_type"
        ),
        {
            "version": version,
            "status": SNAPSHOT_STATUS_BUILDING,
            "started_at": datetime.now().isoformat(),
            "snapshot_type": snapshot_type,
        },
    )
    db.commit()


def activate_snapshot_version(
    db,
    version,
    row_count,
    duration_ms,
    snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES,
):
    ensure_snapshot_meta_row(db, snapshot_type=snapshot_type)
    db.execute(
        text(
            "UPDATE snapshot_build_meta SET "
            "active_version = :version, building_version = NULL, status = :status, "
            "last_built_at = :built_at, last_build_duration_ms = :duration_ms, "
            "last_row_count = :row_count, last_error = NULL "
            "WHERE snapshot_type = :snapshot_type"
        ),
        {
            "version": version,
            "status": SNAPSHOT_STATUS_READY,
            "built_at": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "row_count": row_count,
            "snapshot_type": snapshot_type,
        },
    )
    db.commit()


def set_snapshot_error(db, error_message, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES):
    ensure_snapshot_meta_row(db, snapshot_type=snapshot_type)
    db.execute(
        text(
            "UPDATE snapshot_build_meta SET "
            "status = :status, last_error = :error_message, building_version = NULL "
            "WHERE snapshot_type = :snapshot_type"
        ),
        {
            "status": SNAPSHOT_STATUS_ERROR,
            "error_message": error_message,
            "snapshot_type": snapshot_type,
        },
    )
    db.commit()


def new_snapshot_version(prefix="candidate"):
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def clear_snapshot_version(db, version):
    db.execute(
        text("DELETE FROM alert_candidate_snapshot_badges WHERE snapshot_version = :version"),
        {"version": version},
    )
    db.execute(
        text("DELETE FROM alert_candidate_snapshot_tags WHERE snapshot_version = :version"),
        {"version": version},
    )
    db.execute(
        text("DELETE FROM alert_candidate_snapshots WHERE snapshot_version = :version"),
        {"version": version},
    )


def serialize_json(value, default):
    if value is None:
        value = default
    return json.dumps(value, ensure_ascii=False)


def _cleanup_old_versions(db, keep=2):
    """Delete old snapshot versions, keeping only the most recent N."""
    versions = db.execute(text(
        "SELECT DISTINCT snapshot_version FROM alert_candidate_snapshots "
        "ORDER BY snapshot_version DESC"
    )).fetchall()
    version_list = [r[0] for r in versions]
    if len(version_list) <= keep:
        return
    to_delete = version_list[keep:]
    # Also check active_version — never delete it
    active = get_active_snapshot_version(db)
    to_delete = [v for v in to_delete if v != active]
    if not to_delete:
        return
    placeholders = ", ".join(f":v_{i}" for i in range(len(to_delete)))
    params = {f"v_{i}": v for i, v in enumerate(to_delete)}
    db.execute(
        text(f"DELETE FROM alert_candidate_snapshot_badges WHERE snapshot_version IN ({placeholders})"),
        params,
    )
    db.execute(
        text(f"DELETE FROM alert_candidate_snapshot_tags WHERE snapshot_version IN ({placeholders})"),
        params,
    )
    db.execute(
        text(f"DELETE FROM alert_candidate_snapshots WHERE snapshot_version IN ({placeholders})"),
        params,
    )


# ---------------------------------------------------------------------------
# Snapshot row from candidate (updated with new JSON columns)
# ---------------------------------------------------------------------------

def _snapshot_row_from_candidate(item, snapshot_version):
    priority_value = item.get("candidate_priority")
    if isinstance(priority_value, dict):
        priority = priority_value
    else:
        priority = {
            "id": priority_value,
            "label": item.get("candidate_priority_label"),
            "rank": (item.get("sort_signals") or {}).get("priority_rank", 0),
        }
    event_info = item.get("event")
    trace_info = item.get("traced")
    device_event_info = item.get("device_event")
    return {
        "alert_id": item.get("id"),
        "snapshot_version": snapshot_version,
        "device_id": item.get("device_id") or "",
        "target": item.get("target") or "",
        "port": item.get("port") or "",
        "source_ip": item.get("source_ip"),
        "source_ips": item.get("source_ips"),
        "source_ip_count": item.get("source_ip_count") or 0,
        "target_type": item.get("target_type"),
        "target_kind": item.get("target_kind"),
        "target_kind_label": item.get("target_kind_label"),
        "threat_type": item.get("threat_type"),
        "threat_level": item.get("threat_level"),
        "std_apt_org": item.get("std_apt_org"),
        "apt_org": item.get("apt_org"),
        "apt_org_tier": item.get("apt_org_tier"),
        "vendors": item.get("vendors"),
        "protocol": item.get("protocol"),
        "intel_tags": item.get("intel_tags"),
        "dns_resolved_ip": item.get("dns_resolved_ip"),
        "asset_type": item.get("asset_type"),
        "analysis_status": item.get("analysis_status") or "",
        "is_focused": 1 if item.get("is_focused") else 0,
        "alert_count": item.get("alert_count") or 0,
        "first_alert_time": item.get("first_alert_time"),
        "last_alert_time": item.get("last_alert_time"),
        "heat_target_alert_count": (item.get("heat") or {}).get("target_alert_count", 0),
        "heat_target_device_count": (item.get("heat") or {}).get("target_device_count", 0),
        "heat_device_alert_count": (item.get("heat") or {}).get("device_alert_count", 0),
        "heat_device_target_count": (item.get("heat") or {}).get("device_target_count", 0),
        "heat_source_ip_alert_count": (item.get("heat") or {}).get("source_ip_alert_count", 0),
        "candidate_score": item.get("candidate_score") or 0,
        "candidate_priority": priority.get("id"),
        "candidate_priority_label": priority.get("label"),
        "candidate_rule_ids_json": serialize_json(item.get("candidate_rule_ids"), []),
        "candidate_reasons_json": serialize_json(item.get("candidate_reasons"), []),
        "event_json": serialize_json(event_info, None) if event_info else None,
        "event_status": item.get("event_status"),
        "device_event_json": serialize_json(device_event_info, None) if device_event_info else None,
        "trace_json": serialize_json(trace_info, None) if trace_info else None,
        "trace_status": item.get("trace_status"),
        "ioc_note": item.get("ioc_note"),
        "badges_json": serialize_json(item.get("badges") or [], []),
        "device_tags_json": serialize_json(item.get("device_tags") or [], []),
        "cross_day": 1 if any((badge or {}).get("name") == "cross_day" for badge in (item.get("badges") or [])) else 0,
        "lateral": 1 if any((badge or {}).get("name") == "lateral" for badge in (item.get("badges") or [])) else 0,
        "heat_summary_json": serialize_json(item.get("heat_summary"), {}),
        "relation_summary": item.get("relation_summary"),
        "candidate_summary": item.get("candidate_summary"),
        "candidate_focus": item.get("candidate_focus"),
        "device_note_summary": item.get("device_note_summary"),
        "sort_priority_rank": (item.get("sort_signals") or {}).get("priority_rank", 0),
        "sort_rule_hits": (item.get("sort_signals") or {}).get("rule_hits", 0),
        "sort_target_device_count": (item.get("sort_signals") or {}).get("target_device_count", 0),
        "sort_target_alert_count": (item.get("sort_signals") or {}).get("target_alert_count", 0),
        "sort_source_ip_alert_count": (item.get("sort_signals") or {}).get("source_ip_alert_count", 0),
        "sort_trace_status": (item.get("sort_signals") or {}).get("trace_status"),
        "sort_event_status": (item.get("sort_signals") or {}).get("event_status"),
        "updated_at": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Full rebuild (existing, enhanced)
# ---------------------------------------------------------------------------

def rebuild_candidate_snapshots(db):
    from backend.api import alerts

    started_at = datetime.now()
    if not _snapshot_build_lock.acquire(blocking=False):
        return {"ok": False, "reason": "build_in_progress"}

    snapshot_version = new_snapshot_version()
    try:
        set_snapshot_building(db, snapshot_version)
        clear_snapshot_version(db, snapshot_version)

        where, params = alerts._build_where(
            date_start=None,
            date_end=None,
            target_type=None,
            device_tags=None,
            exclude_device_tags=None,
            threat_types=None,
            threat_levels=None,
            apt_tiers=None,
            hide_traced=False,
            hide_closed=False,
            keyword=None,
            alert_count_max=None,
        )
        all_items, _ = alerts._query_all_candidate_items(
            db,
            where,
            params,
            badges_filter=None,
            target_kind=None,
        )

        next_id = (
            db.execute(text("SELECT COALESCE(MAX(id), 0) FROM alert_candidate_snapshots")).scalar() or 0
        ) + 1
        snapshot_rows = []
        badge_rows = []
        tag_rows = []

        for item in all_items:
            snapshot_id = next_id
            next_id += 1
            row = _snapshot_row_from_candidate(item, snapshot_version)
            row["id"] = snapshot_id
            snapshot_rows.append(row)

            for badge in item.get("badges") or []:
                badge_rows.append(
                    {
                        "snapshot_version": snapshot_version,
                        "snapshot_id": snapshot_id,
                        "badge_name": badge.get("name"),
                        "badge_label": badge.get("label"),
                        "badge_color": badge.get("color"),
                    }
                )

            for tag in item.get("device_tags") or []:
                tag_rows.append(
                    {
                        "snapshot_version": snapshot_version,
                        "snapshot_id": snapshot_id,
                        "tag_id": tag.get("id"),
                        "tag_name": tag.get("name"),
                        "tag_color": tag.get("color"),
                    }
                )

        inserted_rows = len(snapshot_rows)
        if snapshot_rows:
            db.execute(
                text(
                    "INSERT INTO alert_candidate_snapshots ("
                    "id, alert_id, snapshot_version, device_id, target, port, source_ip, source_ips, source_ip_count, "
                    "target_type, target_kind, target_kind_label, threat_type, threat_level, std_apt_org, apt_org, apt_org_tier, "
                    "vendors, protocol, intel_tags, dns_resolved_ip, asset_type, analysis_status, is_focused, "
                    "alert_count, first_alert_time, last_alert_time, "
                    "heat_target_alert_count, heat_target_device_count, heat_device_alert_count, heat_device_target_count, heat_source_ip_alert_count, "
                    "candidate_score, candidate_priority, candidate_priority_label, candidate_rule_ids_json, candidate_reasons_json, "
                    "event_json, event_status, device_event_json, trace_json, trace_status, ioc_note, cross_day, lateral, "
                    "badges_json, device_tags_json, "
                    "heat_summary_json, relation_summary, candidate_summary, candidate_focus, device_note_summary, "
                    "sort_priority_rank, sort_rule_hits, sort_target_device_count, sort_target_alert_count, sort_source_ip_alert_count, "
                    "sort_trace_status, sort_event_status, updated_at"
                    ") VALUES ("
                    ":id, :alert_id, :snapshot_version, :device_id, :target, :port, :source_ip, :source_ips, :source_ip_count, "
                    ":target_type, :target_kind, :target_kind_label, :threat_type, :threat_level, :std_apt_org, :apt_org, :apt_org_tier, "
                    ":vendors, :protocol, :intel_tags, :dns_resolved_ip, :asset_type, :analysis_status, :is_focused, "
                    ":alert_count, :first_alert_time, :last_alert_time, "
                    ":heat_target_alert_count, :heat_target_device_count, :heat_device_alert_count, :heat_device_target_count, :heat_source_ip_alert_count, "
                    ":candidate_score, :candidate_priority, :candidate_priority_label, :candidate_rule_ids_json, :candidate_reasons_json, "
                    ":event_json, :event_status, :device_event_json, :trace_json, :trace_status, :ioc_note, :cross_day, :lateral, "
                    ":badges_json, :device_tags_json, "
                    ":heat_summary_json, :relation_summary, :candidate_summary, :candidate_focus, :device_note_summary, "
                    ":sort_priority_rank, :sort_rule_hits, :sort_target_device_count, :sort_target_alert_count, :sort_source_ip_alert_count, "
                    ":sort_trace_status, :sort_event_status, :updated_at)"
                ),
                snapshot_rows,
            )

        if badge_rows:
            db.execute(
                text(
                    "INSERT INTO alert_candidate_snapshot_badges "
                    "(snapshot_version, snapshot_id, badge_name, badge_label, badge_color) "
                    "VALUES (:snapshot_version, :snapshot_id, :badge_name, :badge_label, :badge_color)"
                ),
                badge_rows,
            )

        if tag_rows:
            db.execute(
                text(
                    "INSERT INTO alert_candidate_snapshot_tags "
                    "(snapshot_version, snapshot_id, tag_id, tag_name, tag_color) "
                    "VALUES (:snapshot_version, :snapshot_id, :tag_id, :tag_name, :tag_color)"
                ),
                tag_rows,
            )

        db.commit()
        duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        activate_snapshot_version(db, snapshot_version, inserted_rows, duration_ms)

        # Clean up old versions
        _cleanup_old_versions(db, keep=2)

        return {
            "ok": True,
            "snapshot_version": snapshot_version,
            "row_count": inserted_rows,
            "duration_ms": duration_ms,
        }
    except Exception as exc:
        db.rollback()
        set_snapshot_error(db, str(exc))
        raise
    finally:
        _snapshot_build_lock.release()


def rebuild_candidate_snapshots_async():
    from backend.utils.db import get_session_local

    def _run():
        session = get_session_local()()
        try:
            rebuild_candidate_snapshots(session)
        finally:
            session.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def request_snapshot_refresh(_scope=None, *_args, **_kwargs):
    """Minimal v2 refresh hook."""
    rebuild_candidate_snapshots_async()


# ---------------------------------------------------------------------------
# Incremental score / reasons / badges recomputation
# ---------------------------------------------------------------------------

def _threat_level_score(value):
    normalized = str(value or "").strip().lower()
    if normalized in {"critical", "high", "高"}:
        return 18
    if normalized in {"medium", "中"}:
        return 8
    if normalized in {"low", "低"}:
        return 3
    return 0


def _tier_score(value):
    normalized = str(value or "").strip().lower()
    if not normalized:
        return 0
    if normalized in {"s", "s级", "a", "a级", "high", "高"}:
        return 16
    if normalized in {"b", "b级", "medium", "中"}:
        return 10
    return 6


def _recompute_score(snap_row, event_info=_UNSET, trace_info=_UNSET, device_tags=_UNSET):
    """Recompute candidate score from static snapshot fields + dynamic overrides."""
    # Static base score from rule IDs
    rule_ids = json.loads(snap_row.get("candidate_rule_ids_json") or "[]")
    rule_score = sum(RULE_SCORE_MAP.get(rid, 0) for rid in rule_ids)

    threat_level_score = _threat_level_score(snap_row.get("threat_level"))
    tier_score = _tier_score(snap_row.get("apt_org_tier"))

    heat_score = (
        min((snap_row.get("heat_target_alert_count", 0) or 0) * 2, 18)
        + min((snap_row.get("heat_target_device_count", 0) or 0) * 6, 24)
        + min((snap_row.get("heat_source_ip_alert_count", 0) or 0) * 2, 14)
        + min((snap_row.get("heat_device_alert_count", 0) or 0), 10)
    )

    vendor_count = len(split_multi_values(snap_row.get("vendors")))
    vendor_score = min(vendor_count * 3, 9) if vendor_count >= 2 else 0

    base_score = rule_score + threat_level_score + tier_score + heat_score + vendor_score

    # Dynamic part: use passed-in data or fall back to snapshot stored values
    if trace_info is _UNSET:
        trace_info = json.loads(snap_row.get("trace_json") or "null")
    if event_info is _UNSET:
        event_info = json.loads(snap_row.get("event_json") or "null")
    if device_tags is _UNSET:
        device_tags = json.loads(snap_row.get("device_tags_json") or "[]")

    dynamic_score = 0
    if trace_info and trace_info.get("active"):
        dynamic_score -= 12
    elif trace_info:
        dynamic_score -= 4
    if event_info:
        dynamic_score += 6
    if device_tags:
        dynamic_score += min(len(device_tags) * 2, 8)

    return base_score + dynamic_score


def _recompute_reasons(snap_row, event_info=_UNSET, trace_info=_UNSET, device_tags=_UNSET):
    """Recompute candidate reasons from static + dynamic data."""
    rule_ids = json.loads(snap_row.get("candidate_rule_ids_json") or "[]")
    reasons = []
    for rid in rule_ids:
        for rule in DEFAULT_CANDIDATE_RULES:
            if rule["id"] == rid:
                reasons.append(rule["label"])
                break

    threat_level = str(snap_row.get("threat_level") or "").strip()
    if threat_level:
        reasons.append(f"威胁等级:{threat_level}")
    if snap_row.get("apt_org_tier"):
        reasons.append(f"APT 分级:{snap_row['apt_org_tier']}")
    vendor_count = len(split_multi_values(snap_row.get("vendors")))
    if vendor_count >= 2:
        reasons.append(f"多厂商同时命中({vendor_count})")

    heat_target_alert = snap_row.get("heat_target_alert_count", 0) or 0
    heat_target_device = snap_row.get("heat_target_device_count", 0) or 0
    heat_source_ip = snap_row.get("heat_source_ip_alert_count", 0) or 0
    heat_device_alert = snap_row.get("heat_device_alert_count", 0) or 0

    if heat_target_device >= 2:
        reasons.append(f"同目标涉及 {heat_target_device} 台设备")
    if heat_target_alert >= 2:
        reasons.append(f"目标热度:{heat_target_alert} 条")
    if heat_source_ip >= 2:
        reasons.append(f"源 IP 热度:{heat_source_ip} 条")
    if heat_device_alert >= 2:
        reasons.append(f"设备热度:{heat_device_alert} 条")

    if trace_info is _UNSET:
        trace_info = json.loads(snap_row.get("trace_json") or "null")
    if event_info is _UNSET:
        event_info = json.loads(snap_row.get("event_json") or "null")
    if device_tags is _UNSET:
        device_tags = json.loads(snap_row.get("device_tags_json") or "[]")

    if trace_info:
        note_preview = trace_info.get("note", "")
        reasons.append(f"IOC备注:{note_preview}" if note_preview else "IOC备注:有记录")
    if event_info:
        reasons.append(f"已关联事件:{event_info.get('event_name')}")
    if device_tags:
        preview = ",".join(tag["name"] for tag in device_tags[:3])
        reasons.append(f"设备标签:{preview}")

    # Deduplicate
    deduped = []
    seen = set()
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return deduped


def _recompute_badges_for_incremental(snap_row, event_info=_UNSET, trace_info=_UNSET, device_tags=_UNSET):
    """Recompute badges for incremental update.
    Static badges are derived from snapshot stored badges_json; only
    event/trace/tag-related relation badges are recomputed."""
    from backend.services import _append_badge

    # Start from static badges (apt_dict, advanced_crime, noise_family, etc.)
    # These don't change during incremental updates, so we keep them as-is
    existing_badges = json.loads(snap_row.get("badges_json") or "[]")
    static_badges = []
    # Static badge names (computed at import time, don't change during incremental patch)
    # KNOWN TRADE-OFF: cross_day and lateral are aggregate badges that depend on
    # the full alert dataset. If underlying alerts are deleted, these badges may
    # become stale in incremental patch. The real-time coverage layer in
    # query_alert_candidates corrects this at query time, so incremental staleness
    # is only visible if the coverage layer is bypassed.
    static_names = {"apt_dict", "advanced_crime", "noise_family", "multi_vendor",
                    "cross_day", "lateral", "expired_revive", "high_tier", "scan_noise"}
    for b in existing_badges:
        if b.get("name") in static_names:
            static_badges.append(b)

    # Recompute relation badges (event, device_tag, traced_history, meta)
    relation_badges = []
    if event_info is not _UNSET and event_info is not None:
        relation_badges.append({
            "name": f"event:{event_info['event_id']}",
            "label": f"事件:{event_info['event_name']}",
            "color": event_info.get("color") or "#409EFF",
        })

    if device_tags is _UNSET:
        device_tags = json.loads(snap_row.get("device_tags_json") or "[]")
    for tag in device_tags:
        relation_badges.append({
            "name": f"device_tag:{tag['id']}",
            "label": f"标签:{tag['name']}",
            "color": tag.get("color") or "#909399",
        })

    if trace_info is _UNSET:
        trace_info = json.loads(snap_row.get("trace_json") or "null")
    if trace_info:
        note_preview = trace_info.get("note", "")
        label = f"IOC备注:{note_preview}" if note_preview else "IOC备注:有记录"
        relation_badges.append({"name": "traced_history", "label": label, "color": "#13c2c2"})

    # Meta badges from static fields
    for threat_type in split_multi_values(snap_row.get("threat_type")):
        relation_badges.append({
            "name": f"meta:threat_type:{threat_type}",
            "label": f"威胁:{threat_type}",
            "color": "#6f42c1",
        })

    std_apt_org = snap_row.get("std_apt_org")
    if std_apt_org:
        relation_badges.append({
            "name": f"meta:std_apt_org:{std_apt_org}",
            "label": f"标准APT:{std_apt_org}",
            "color": "#d9485f",
        })

    apt_org = snap_row.get("apt_org")
    if apt_org:
        relation_badges.append({
            "name": f"meta:apt_org:{apt_org}",
            "label": f"APT:{apt_org}",
            "color": "#fa8c16",
        })

    for vendor in split_multi_values(snap_row.get("vendors")):
        relation_badges.append({
            "name": f"meta:vendor:{vendor}",
            "label": f"厂商:{vendor}",
            "color": "#595959",
        })

    # Deduplicate
    all_badges = static_badges + relation_badges
    seen = set()
    deduped = []
    for badge in all_badges:
        key = (badge.get("name"), badge.get("label"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(badge)
    return deduped


# ---------------------------------------------------------------------------
# Incremental patch functions
# ---------------------------------------------------------------------------

def _snapshot_ids_for_event_scope(db, version, iocs=None, device_ids=None):
    affected_ids = set()
    for (target, port) in (iocs or []):
        if port:
            rows = db.execute(text(
                "SELECT id FROM alert_candidate_snapshots "
                "WHERE snapshot_version = :v AND target = :t AND port = :p"
            ), {"v": version, "t": target, "p": port}).fetchall()
        else:
            rows = db.execute(text(
                "SELECT id FROM alert_candidate_snapshots "
                "WHERE snapshot_version = :v AND target = :t"
            ), {"v": version, "t": target}).fetchall()
        affected_ids.update(r[0] for r in rows)

    for device_id in (device_ids or []):
        did = device_id[0] if isinstance(device_id, tuple) else device_id
        rows = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND UPPER(device_id) = :d"
        ), {"v": version, "d": (did or "").upper()}).fetchall()
        affected_ids.update(r[0] for r in rows)
    return affected_ids


def _patch_snapshot_event_rows(db, version, affected_ids):
    """Recompute event-related fields for affected snapshot rows.

    Instead of rebuilding global event maps from all snapshot rows,
    queries only the changed event's IOCs and devices directly.
    """
    if not affected_ids:
        return

    # Fetch the single event that changed (all affected_ids belong to the same event scope)
    # We query the event IOCs and devices directly rather than rebuilding full maps
    placeholders = ", ".join(f":id_{i}" for i in range(len(affected_ids)))
    params = {f"id_{i}": sid for i, sid in enumerate(affected_ids)}

    # Get the event that these rows should match — query all active events
    # and check which one matches the affected rows' IOC/device combos
    event_rows = db.execute(text(
        "SELECT me.id, me.event_name, me.color, me.status "
        "FROM mined_events me WHERE me.status IS NULL OR me.status != 'closed'"
    )).fetchall()

    # Build event IOC and device lookups (only for active events)
    event_iocs = {}  # event_id -> [(target, port)]
    event_devices = {}  # event_id -> [device_id]
    for er in event_rows:
        eid = er[0]
        ioc_list = db.execute(text(
            "SELECT target, COALESCE(port, '') FROM mined_event_iocs WHERE event_id = :eid"
        ), {"eid": eid}).fetchall()
        event_iocs[eid] = [(t, p) for t, p in ioc_list]
        dev_list = db.execute(text(
            "SELECT device_id FROM mined_event_devices WHERE event_id = :eid"
        ), {"eid": eid}).fetchall()
        event_devices[eid] = [d[0].upper() for d in dev_list if d[0]]

    # For each affected row, find matching event
    for snap_id in affected_ids:
        snap_row_dict = db.execute(text(
            "SELECT * FROM alert_candidate_snapshots WHERE id = :id"
        ), {"id": snap_id}).fetchone()
        if not snap_row_dict:
            continue
        snap = dict(snap_row_dict._mapping)

        target = snap.get("target", "")
        port = snap.get("port", "")
        device_id_upper = (snap.get("device_id", "") or "").upper()

        # Find matching event
        new_event_info = None
        device_event = None
        for er in event_rows:
            eid = er[0]
            event_info = {
                "event_id": eid,
                "event_name": er[1],
                "color": er[2],
                "status": er[3],
            }

            # Check IOC match (exact or wildcard with empty port)
            for ioc_target, ioc_port in event_iocs[eid]:
                if ioc_target == target and ioc_port == port:
                    new_event_info = event_info
                    break
                if ioc_port == "" and ioc_target == target:
                    new_event_info = event_info
                    break

            # Check device event match (event must have both matching device AND IOC)
            if device_id_upper in event_devices[eid]:
                for ioc_target, ioc_port in event_iocs[eid]:
                    if ioc_target == target and (ioc_port == port or ioc_port == ""):
                        device_event = event_info
                        break

        new_score = _recompute_score(snap, event_info=new_event_info)
        new_priority = classify_candidate_priority(new_score)
        new_reasons = _recompute_reasons(snap, event_info=new_event_info)
        new_badges = _recompute_badges_for_incremental(snap, event_info=new_event_info)

        db.execute(text("""
            UPDATE alert_candidate_snapshots SET
                event_json = :event_json,
                event_status = :event_status,
                device_event_json = :device_event_json,
                candidate_score = :score,
                candidate_priority = :priority,
                candidate_priority_label = :priority_label,
                candidate_reasons_json = :reasons,
                badges_json = :badges_json,
                sort_priority_rank = :priority_rank,
                sort_event_status = :event_status_val,
                relation_summary = :relation_summary,
                candidate_summary = :candidate_summary,
                updated_at = :updated_at
            WHERE id = :id
        """), {
            "id": snap_id,
            "event_json": json.dumps(new_event_info, ensure_ascii=False) if new_event_info else None,
            "event_status": new_event_info.get("status") if new_event_info else None,
            "event_status_val": new_event_info.get("status") if new_event_info else None,
            "device_event_json": json.dumps(device_event, ensure_ascii=False) if device_event else None,
            "score": new_score,
            "priority": new_priority["id"],
            "priority_label": new_priority["label"],
            "priority_rank": new_priority["rank"],
            "reasons": json.dumps(new_reasons, ensure_ascii=False),
            "badges_json": json.dumps(new_badges, ensure_ascii=False),
            "relation_summary": " | ".join(
                [b["label"] for b in _build_relation_badges_for_summary(snap, new_event_info, json.loads(snap.get("device_tags_json") or "[]"), json.loads(snap.get("trace_json") or "null"))]
            ),
            "candidate_summary": " | ".join(new_reasons[:4]),
            "updated_at": datetime.now().isoformat(),
        })

    # Sync badge subtable
    _sync_badge_subtable(db, version, affected_ids)


def patch_snapshot_for_event_scope(db, iocs=None, device_ids=None):
    """Recompute event fields for rows affected by IOC/device scope changes."""
    version = get_active_snapshot_version(db)
    if not version:
        return
    affected_ids = _snapshot_ids_for_event_scope(db, version, iocs=iocs, device_ids=device_ids)
    _patch_snapshot_event_rows(db, version, affected_ids)


def patch_snapshot_for_event(db, event_id):
    """Event changed — update affected snapshot rows."""
    iocs = db.execute(text(
        "SELECT target, COALESCE(port, '') FROM mined_event_iocs WHERE event_id = :eid"
    ), {"eid": event_id}).fetchall()
    device_ids = db.execute(text(
        "SELECT device_id FROM mined_event_devices WHERE event_id = :eid"
    ), {"eid": event_id}).fetchall()

    if not iocs and not device_ids:
        return

    patch_snapshot_for_event_scope(db, iocs=iocs, device_ids=device_ids)


def patch_snapshot_for_trace(db, target, port):
    """IOC note changed — update affected snapshot rows."""
    version = get_active_snapshot_version(db)
    if not version:
        return

    # Find affected rows
    if port:
        affected = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND target = :t AND port = :p"
        ), {"v": version, "t": target, "p": port}).fetchall()
    else:
        affected = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND target = :t"
        ), {"v": version, "t": target}).fetchall()

    if not affected:
        return

    # Reload trace info
    from backend.api import alerts as alerts_mod
    trace_index = alerts_mod._preload_trace_index(db)
    trace_info = trace_index.get((target, port or ""))
    trace_info = trace_info[0] if trace_info else None
    if trace_info:
        trace_info = {
            "target": target,
            "port": port or "",
            "traced_at": trace_info.get("traced_at"),
            "note": trace_info.get("note", ""),
        }
        # Determine active status
        cfg = get_config()
        ttl_days = cfg.get("rules", {}).get("trace_ttl_days", 30)
        from backend.services import _is_trace_expired
        trace_info["active"] = not _is_trace_expired(trace_info, ttl_days)

    affected_ids = [r[0] for r in affected]
    trace_status = (
        "active" if trace_info and trace_info.get("active")
        else "expired" if trace_info
        else "none"
    )

    for (snap_id,) in affected:
        snap_row_dict = db.execute(text(
            "SELECT * FROM alert_candidate_snapshots WHERE id = :id"
        ), {"id": snap_id}).fetchone()
        if not snap_row_dict:
            continue
        snap = dict(snap_row_dict._mapping)

        new_score = _recompute_score(snap, trace_info=trace_info)
        new_priority = classify_candidate_priority(new_score)
        new_reasons = _recompute_reasons(snap, trace_info=trace_info)
        new_badges = _recompute_badges_for_incremental(snap, trace_info=trace_info)

        db.execute(text("""
            UPDATE alert_candidate_snapshots SET
                trace_json = :trace_json,
                trace_status = :trace_status,
                ioc_note = :ioc_note,
                candidate_score = :score,
                candidate_priority = :priority,
                candidate_priority_label = :priority_label,
                candidate_reasons_json = :reasons,
                badges_json = :badges_json,
                sort_priority_rank = :priority_rank,
                sort_trace_status = :trace_status_val,
                relation_summary = :relation_summary,
                candidate_summary = :candidate_summary,
                updated_at = :updated_at
            WHERE id = :id
        """), {
            "id": snap_id,
            "trace_json": json.dumps(trace_info, ensure_ascii=False) if trace_info else None,
            "trace_status": trace_status,
            "trace_status_val": trace_status,
            "ioc_note": trace_info.get("note") if trace_info else None,
            "score": new_score,
            "priority": new_priority["id"],
            "priority_label": new_priority["label"],
            "priority_rank": new_priority["rank"],
            "reasons": json.dumps(new_reasons, ensure_ascii=False),
            "badges_json": json.dumps(new_badges, ensure_ascii=False),
            "relation_summary": " | ".join(
                [b["label"] for b in _build_relation_badges_for_summary(
                    snap,
                    json.loads(snap.get("event_json") or "null"),
                    json.loads(snap.get("device_tags_json") or "[]"),
                    trace_info,
                )]
            ),
            "candidate_summary": " | ".join(new_reasons[:4]),
            "updated_at": datetime.now().isoformat(),
        })

    _sync_badge_subtable(db, version, affected_ids)


def patch_snapshot_for_device_tags(db, device_ids):
    """Device tags changed — update affected snapshot rows.

    Collects all affected snapshot IDs and tag mappings first,
    then batches the tag subtable sync in a single pass.
    """
    version = get_active_snapshot_version(db)
    if not version:
        return

    from backend.api import alerts as alerts_mod

    all_affected_ids = []
    # Collect device→tags mappings for batch subtable sync
    device_tags_map = {}  # device_id (upper) -> tags list

    for device_id in device_ids:
        did_upper = (device_id or "").upper()
        affected = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND UPPER(device_id) = :d"
        ), {"v": version, "d": did_upper}).fetchall()

        if not affected:
            continue

        # Reload device tags — collect once per unique device
        if did_upper not in device_tags_map:
            fake_rows = [type('FakeRow', (), {'_mapping': {'device_id': device_id}})()]
            tag_map = alerts_mod._device_tag_map_for_rows(db, fake_rows)
            device_tags_map[did_upper] = tag_map.get(did_upper, [])
        new_tags = device_tags_map[did_upper]
        tags_json = json.dumps(new_tags, ensure_ascii=False)
        note_summary = " | ".join(tag["name"] for tag in new_tags)

        for (snap_id,) in affected:
            snap_row_dict = db.execute(text(
                "SELECT * FROM alert_candidate_snapshots WHERE id = :id"
            ), {"id": snap_id}).fetchone()
            if not snap_row_dict:
                continue
            snap = dict(snap_row_dict._mapping)

            new_score = _recompute_score(snap, device_tags=new_tags)
            new_priority = classify_candidate_priority(new_score)
            new_reasons = _recompute_reasons(snap, device_tags=new_tags)
            new_badges = _recompute_badges_for_incremental(snap, device_tags=new_tags)

            db.execute(text("""
                UPDATE alert_candidate_snapshots SET
                    device_tags_json = :tags_json,
                    device_note_summary = :note_summary,
                    candidate_score = :score,
                    candidate_priority = :priority,
                    candidate_priority_label = :priority_label,
                    candidate_reasons_json = :reasons,
                    badges_json = :badges_json,
                    sort_priority_rank = :priority_rank,
                    relation_summary = :relation_summary,
                    candidate_summary = :candidate_summary,
                    updated_at = :updated_at
                WHERE id = :id
            """), {
                "id": snap_id,
                "tags_json": tags_json,
                "note_summary": note_summary,
                "score": new_score,
                "priority": new_priority["id"],
                "priority_label": new_priority["label"],
                "priority_rank": new_priority["rank"],
                "reasons": json.dumps(new_reasons, ensure_ascii=False),
                "badges_json": json.dumps(new_badges, ensure_ascii=False),
                "relation_summary": " | ".join(
                    [b["label"] for b in _build_relation_badges_for_summary(
                        snap,
                        json.loads(snap.get("event_json") or "null"),
                        new_tags,
                        json.loads(snap.get("trace_json") or "null"),
                    )]
                ),
                "candidate_summary": " | ".join(new_reasons[:4]),
                "updated_at": datetime.now().isoformat(),
            })

            all_affected_ids.append(snap_id)

    # Batch sync all tag subtables in one pass
    _sync_tag_subtable_batch(db, version, device_tags_map)

    if all_affected_ids:
        _sync_badge_subtable(db, version, all_affected_ids)


def patch_snapshot_for_tag_color(db, tag_id):
    """Tag color changed — refresh affected devices in snapshot JSON and tag subtable."""
    version = get_active_snapshot_version(db)
    if not version:
        return

    device_ids = [
        row[0] for row in db.execute(text(
            "SELECT DISTINCT device_id FROM device_tags WHERE tag_id = :id"
        ), {"id": tag_id}).fetchall()
    ]
    if not device_ids:
        return

    patch_snapshot_for_device_tags(db, device_ids)


# ---------------------------------------------------------------------------
# Subtable sync helpers
# ---------------------------------------------------------------------------

def _sync_badge_subtable(db, version, affected_ids):
    """Re-sync badge subtable for affected snapshot rows."""
    if not affected_ids:
        return
    placeholders = ", ".join(f":id_{i}" for i in range(len(affected_ids)))
    params = {f"id_{i}": sid for i, sid in enumerate(affected_ids)}
    params["version"] = version

    # Delete existing badges for affected rows
    db.execute(text(
        f"DELETE FROM alert_candidate_snapshot_badges "
        f"WHERE snapshot_version = :version AND snapshot_id IN ({placeholders})"
    ), params)

    # Re-insert from badges_json
    rows = db.execute(text(
        f"SELECT id, badges_json FROM alert_candidate_snapshots "
        f"WHERE snapshot_version = :version AND id IN ({placeholders})"
    ), params).fetchall()

    badge_rows = []
    for row in rows:
        snap_id = row[0]
        badges = json.loads(row[1] or "[]")
        for badge in badges:
            # Only insert non-meta badges (static + relation badges that are in subtable)
            badge_name = badge.get("name", "")
            if badge_name.startswith(("event:", "device_tag:", "traced_history", "meta:")):
                continue  # These are dynamic relation badges, not in subtable
            badge_rows.append({
                "snapshot_version": version,
                "snapshot_id": snap_id,
                "badge_name": badge.get("name"),
                "badge_label": badge.get("label"),
                "badge_color": badge.get("color"),
            })

    if badge_rows:
        db.execute(
            text(
                "INSERT INTO alert_candidate_snapshot_badges "
                "(snapshot_version, snapshot_id, badge_name, badge_label, badge_color) "
                "VALUES (:snapshot_version, :snapshot_id, :badge_name, :badge_label, :badge_color)"
            ),
            badge_rows,
        )


def _sync_tag_subtable(db, version, device_id, tags):
    """Re-sync tag subtable for a device's snapshot rows."""
    snap_ids = db.execute(text(
        "SELECT id FROM alert_candidate_snapshots "
        "WHERE snapshot_version = :v AND UPPER(device_id) = :d"
    ), {"v": version, "d": (device_id or "").upper()}).fetchall()

    if not snap_ids:
        return

    # Delete existing tags for these snapshot rows
    placeholders = ", ".join(f":sid_{i}" for i in range(len(snap_ids)))
    params = {"version": version, **{f"sid_{i}": r[0] for i, r in enumerate(snap_ids)}}
    db.execute(text(
        f"DELETE FROM alert_candidate_snapshot_tags "
        f"WHERE snapshot_version = :version AND snapshot_id IN ({placeholders})"
    ), params)

    # Re-insert current tags. If tags is empty, the delete above is the desired state.
    tag_rows = []
    for (snap_id,) in snap_ids:
        for tag in tags:
            tag_rows.append({
                "snapshot_version": version,
                "snapshot_id": snap_id,
                "tag_id": tag["id"],
                "tag_name": tag["name"],
                "tag_color": tag["color"],
            })

    if tag_rows:
        db.execute(
            text(
                "INSERT INTO alert_candidate_snapshot_tags "
                "(snapshot_version, snapshot_id, tag_id, tag_name, tag_color) "
                "VALUES (:snapshot_version, :snapshot_id, :tag_id, :tag_name, :tag_color)"
            ),
            tag_rows,
        )


def _sync_tag_subtable_batch(db, version, device_tags_map):
    """Batch sync tag subtables for multiple devices in one pass.

    device_tags_map: dict of device_id (UPPER) -> tags list.
    Replaces N individual _sync_tag_subtable calls with a single
    DELETE + INSERT for all affected devices.
    """
    if not device_tags_map:
        return

    # Collect all snapshot IDs grouped by device_id
    device_snap_ids = {}  # device_id (upper) -> [snap_id, ...]
    for did_upper in device_tags_map:
        snap_ids = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND UPPER(device_id) = :d"
        ), {"v": version, "d": did_upper}).fetchall()
        if snap_ids:
            device_snap_ids[did_upper] = [r[0] for r in snap_ids]

    if not device_snap_ids:
        return

    # Flatten all snapshot IDs
    all_snap_ids = []
    for sids in device_snap_ids.values():
        all_snap_ids.extend(sids)

    # Delete existing tags for all affected snapshot rows
    placeholders = ", ".join(f":sid_{i}" for i in range(len(all_snap_ids)))
    params = {"version": version, **{f"sid_{i}": sid for i, sid in enumerate(all_snap_ids)}}
    db.execute(text(
        f"DELETE FROM alert_candidate_snapshot_tags "
        f"WHERE snapshot_version = :version AND snapshot_id IN ({placeholders})"
    ), params)

    # Re-insert tags for all devices
    tag_rows = []
    for did_upper, snap_ids in device_snap_ids.items():
        tags = device_tags_map.get(did_upper, [])
        for snap_id in snap_ids:
            for tag in tags:
                tag_rows.append({
                    "snapshot_version": version,
                    "snapshot_id": snap_id,
                    "tag_id": tag["id"],
                    "tag_name": tag["name"],
                    "tag_color": tag["color"],
                })

    if tag_rows:
        db.execute(
            text(
                "INSERT INTO alert_candidate_snapshot_tags "
                "(snapshot_version, snapshot_id, tag_id, tag_name, tag_color) "
                "VALUES (:snapshot_version, :snapshot_id, :tag_id, :tag_name, :tag_color)"
            ),
            tag_rows,
        )


def _build_relation_badges_for_summary(row_dict, event_info, device_tags, trace_info):
    """Build relation badges list (for relation_summary field)."""
    badges = []
    if event_info:
        badges.append({
            "name": f"event:{event_info['event_id']}",
            "label": f"事件:{event_info['event_name']}",
            "color": event_info.get("color") or "#409EFF",
        })
    for tag in device_tags:
        badges.append({
            "name": f"device_tag:{tag['id']}",
            "label": f"标签:{tag['name']}",
            "color": tag.get("color") or "#909399",
        })
    if trace_info:
        note_preview = trace_info.get("note", "")
        label = f"IOC备注:{note_preview}" if note_preview else "IOC备注:有记录"
        badges.append({"name": "traced_history", "label": label, "color": "#13c2c2"})
    for threat_type in split_multi_values(row_dict.get("threat_type")):
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
    for vendor in split_multi_values(row_dict.get("vendors")):
        badges.append({
            "name": f"meta:vendor:{vendor}",
            "label": f"厂商:{vendor}",
            "color": "#595959",
        })
    return badges
