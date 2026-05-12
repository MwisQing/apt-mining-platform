import json
import threading
import uuid
from datetime import datetime

from sqlalchemy import text

SNAPSHOT_TYPE_ALERT_CANDIDATES = "alert_candidates"
SNAPSHOT_STATUS_IDLE = "idle"
SNAPSHOT_STATUS_BUILDING = "building"
SNAPSHOT_STATUS_READY = "ready"
SNAPSHOT_STATUS_ERROR = "error"

_snapshot_build_lock = threading.Lock()


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
    meta = get_snapshot_meta(db, snapshot_type=snapshot_type)
    return meta.get("active_version") if meta else None


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
    return {
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
        "trace_json": serialize_json(trace_info, None) if trace_info else None,
        "trace_status": item.get("trace_status"),
        "ioc_note": item.get("ioc_note"),
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
                    "id, snapshot_version, device_id, target, port, source_ip, source_ips, source_ip_count, "
                    "target_type, target_kind, target_kind_label, threat_type, threat_level, std_apt_org, apt_org, apt_org_tier, "
                    "vendors, protocol, intel_tags, dns_resolved_ip, asset_type, analysis_status, is_focused, "
                    "alert_count, first_alert_time, last_alert_time, "
                    "heat_target_alert_count, heat_target_device_count, heat_device_alert_count, heat_device_target_count, heat_source_ip_alert_count, "
                    "candidate_score, candidate_priority, candidate_priority_label, candidate_rule_ids_json, candidate_reasons_json, "
                    "event_json, event_status, trace_json, trace_status, ioc_note, cross_day, lateral, "
                    "heat_summary_json, relation_summary, candidate_summary, candidate_focus, device_note_summary, "
                    "sort_priority_rank, sort_rule_hits, sort_target_device_count, sort_target_alert_count, sort_source_ip_alert_count, "
                    "sort_trace_status, sort_event_status, updated_at"
                    ") VALUES ("
                    ":id, :snapshot_version, :device_id, :target, :port, :source_ip, :source_ips, :source_ip_count, "
                    ":target_type, :target_kind, :target_kind_label, :threat_type, :threat_level, :std_apt_org, :apt_org, :apt_org_tier, "
                    ":vendors, :protocol, :intel_tags, :dns_resolved_ip, :asset_type, :analysis_status, :is_focused, "
                    ":alert_count, :first_alert_time, :last_alert_time, "
                    ":heat_target_alert_count, :heat_target_device_count, :heat_device_alert_count, :heat_device_target_count, :heat_source_ip_alert_count, "
                    ":candidate_score, :candidate_priority, :candidate_priority_label, :candidate_rule_ids_json, :candidate_reasons_json, "
                    ":event_json, :event_status, :trace_json, :trace_status, :ioc_note, :cross_day, :lateral, "
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
    """Minimal v2 refresh hook.

    For now we use async full rebuilds after data mutations to keep snapshot data
    fresh and correct. Once the main path is stable, this can be refined into
    true incremental refreshes with queue coalescing.
    """
    rebuild_candidate_snapshots_async()
