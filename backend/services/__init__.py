from datetime import datetime, timedelta

from backend.utils import get_advanced_crime, get_apt_dict, get_config, get_noise_family


def _append_badge(badges, name, label, color):
    for badge in badges:
        if badge.get("name") == name or badge.get("label") == label:
            return
    badges.append({"name": name, "label": label, "color": color})


def _is_trace_expired(trace_info, ttl_days):
    if not trace_info:
        return False
    traced_at = trace_info.get("traced_at")
    if not traced_at:
        return False
    text_value = str(traced_at).strip().replace(" ", "T")
    try:
        traced_at_dt = datetime.fromisoformat(text_value)
    except ValueError:
        return False
    return traced_at_dt < datetime.now() - timedelta(days=ttl_days)


def _build_trace_index(all_trace_rows):
    """Pre-build (target, port) → list of trace info dict for O(1) lookup."""
    index = {}
    for row in all_trace_rows:
        target = row[0]
        port = row[1] or ""
        info = {"traced_at": str(row[2]) if row[2] else None, "note": row[3]}
        index.setdefault((target, port), []).append(info)
    return index


def compute_badges(alert_row, cross_day_pairs=None, lateral_ips=None, db=None, trace_info=None, trace_index=None):
    """Compute badges for an alert row.

    trace_index: pre-built (target, port) → list of trace info dict. Replaces N+1 SQL queries.
    """
    if cross_day_pairs is None:
        cross_day_pairs = set()
    if lateral_ips is None:
        lateral_ips = set()

    badges = []
    cfg = get_config()
    enabled = cfg.get("badges", {}).get("enabled", [])
    thresholds = cfg.get("badges", {}).get("thresholds", {})

    if "apt_dict" in enabled and alert_row.std_apt_org and alert_row.std_apt_org.lower() in get_apt_dict():
        _append_badge(badges, "apt_dict", "APT词典", "red")

    if "advanced_crime" in enabled and alert_row.apt_org:
        advanced_crime = get_advanced_crime()
        apt_org = alert_row.apt_org
        if apt_org.lower() in advanced_crime or apt_org in advanced_crime:
            _append_badge(badges, "advanced_crime", "高级黑灰产", "purple")

    if "noise_family" in enabled and alert_row.threat_type:
        noise_family = get_noise_family()
        for tag in str(alert_row.threat_type).split(","):
            if tag.strip().lower() in noise_family:
                _append_badge(badges, "noise_family", "噪声家族", "gray")
                break

    if "multi_vendor" in enabled and alert_row.vendors:
        vendor_count = len([value for value in str(alert_row.vendors).split(",") if value.strip()])
        if vendor_count >= thresholds.get("multi_vendor_min", 3):
            _append_badge(badges, "multi_vendor", "多厂商", "yellow")

    if "cross_day" in enabled and (alert_row.source_ip, alert_row.target) in cross_day_pairs:
        _append_badge(badges, "cross_day", "跨天持续", "green")

    if "lateral" in enabled and alert_row.source_ip in lateral_ips:
        _append_badge(badges, "lateral", "横向扩散", "blue")

    if "expired_revive" in enabled:
        ttl_days = cfg.get("rules", {}).get("trace_ttl_days", 30)
        expired = _is_trace_expired(trace_info, ttl_days)
        if not expired and trace_index is not None:
            # Use pre-built index instead of per-row SQL query
            ttl_cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
            port_match = alert_row.port if alert_row.port else ""
            all_traces = trace_index.get((alert_row.target, port_match), [])
            expired = any(
                t["traced_at"] and str(t["traced_at"]) < ttl_cutoff for t in all_traces
            )
        elif not expired and db is not None and trace_index is None:
            # Fallback: legacy per-row query (only if index not provided)
            ttl_cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
            port_match = alert_row.port if alert_row.port else ""
            rows = db.execute(
                "SELECT traced_at FROM traced_targets "
                "WHERE target = :target AND COALESCE(port, '') = :port",
                {"target": alert_row.target, "port": port_match},
            ).fetchall()
            expired = any(row[0] and str(row[0]) < ttl_cutoff for row in rows)
        if expired:
            _append_badge(badges, "expired_revive", "追踪过期", "orange")

    if "high_tier" in enabled and alert_row.apt_org_tier == "一级":
        _append_badge(badges, "high_tier", "高级别", "gold")

    if "scan_noise" in enabled and alert_row.alert_count and alert_row.alert_count > thresholds.get("scan_noise_count", 1000):
        _append_badge(badges, "scan_noise", "疑似扫描", "lightgray")

    return badges
