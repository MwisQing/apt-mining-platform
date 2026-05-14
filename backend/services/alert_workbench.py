import hashlib
import ipaddress
import json
import re


MULTI_VALUE_SPLIT_RE = re.compile(r"[,;/|\uFF0C\uFF1B\u3001\n\r]+")

DEFAULT_CANDIDATE_RULES = (
    {
        "id": "threat_type_apt",
        "label": "\u5a01\u80c1\u7c7b\u578b\u547d\u4e2d APT",
        "field": "threat_type",
        "keywords": ("apt",),
        "score": 34,
    },
    {
        "id": "threat_type_remote_control",
        "label": "\u5a01\u80c1\u7c7b\u578b\u547d\u4e2d \u8fdc\u63a7/remote",
        "field": "threat_type",
        "keywords": ("\u8FDC\u63A7", "remote"),
        "score": 30,
    },
    {
        "id": "std_apt_org_present",
        "label": "\u5df2\u6620\u5c04\u6807\u51c6 APT \u7ec4\u7ec7",
        "field": "std_apt_org",
        "presence": True,
        "score": 26,
    },
    {
        "id": "apt_org_present",
        "label": "\u539f\u59cb APT \u7ec4\u7ec7\u5b57\u6bb5\u975e\u7a7a",
        "field": "apt_org",
        "presence": True,
        "score": 22,
    },
    {
        "id": "intel_tags_c2_remote",
        "label": "\u60c5\u62a5\u6807\u7b7e\u547d\u4e2d APT/C2/\u8fdc\u63a7",
        "field": "intel_tags",
        "keywords": ("apt", "c2", "\u8FDC\u63A7", "remote"),
        "score": 18,
    },
)

ALERT_CONTENT_FIELDS = (
    "device_id",
    "first_alert_time",
    "last_alert_time",
    "source_ip",
    "target",
    "target_type",
    "port",
    "threat_type",
    "threat_level",
    "std_apt_org",
    "apt_org",
    "apt_org_tier",
    "alert_count",
    "vendors",
    "protocol",
    "intel_tags",
    "dns_resolved_ip",
    "down_traffic",
    "up_traffic",
    "asset_type",
)


def split_multi_values(value):
    if value is None:
        return []
    return [part.strip() for part in MULTI_VALUE_SPLIT_RE.split(str(value)) if part.strip()]


def _normalize_text(value):
    return str(value or "").strip().lower()


def _extract_field_value(row_or_value, field):
    if isinstance(row_or_value, dict):
        return row_or_value.get(field)
    return getattr(row_or_value, field, None)


def _field_matches_rule(value, rule):
    normalized = _normalize_text(value)
    if rule.get("presence"):
        return bool(normalized)
    return any(keyword.lower() in normalized for keyword in rule.get("keywords", ()))


def _tier_score(value):
    normalized = _normalize_text(value)
    if not normalized:
        return 0
    if normalized in {"s", "s\u7ea7", "a", "a\u7ea7", "high", "\u9ad8"}:
        return 16
    if normalized in {"b", "b\u7ea7", "medium", "\u4e2d"}:
        return 10
    return 6


def _threat_level_score(value):
    normalized = _normalize_text(value)
    if normalized in {"critical", "high", "\u9ad8"}:
        return 18
    if normalized in {"medium", "\u4e2d"}:
        return 8
    if normalized in {"low", "\u4f4e"}:
        return 3
    return 0


def build_candidate_rule_sql(rules=DEFAULT_CANDIDATE_RULES, *, table_alias="a", prefix="candidate_kw"):
    clauses = []
    params = {}
    for rule_index, rule in enumerate(rules):
        field = rule["field"]
        if rule.get("presence"):
            clauses.append(f"COALESCE({table_alias}.{field}, '') != ''")
            continue
        rule_clauses = []
        for keyword_index, keyword in enumerate(rule.get("keywords", ())):
            key = f"{prefix}_{rule_index}_{keyword_index}"
            rule_clauses.append(f"LOWER(COALESCE({table_alias}.{field}, '')) LIKE :{key}")
            params[key] = f"%{keyword.lower()}%"
        if rule_clauses:
            clauses.append("(" + " OR ".join(rule_clauses) + ")")
    if not clauses:
        return "1=0", params
    return "(" + " OR ".join(clauses) + ")", params


def classify_target_kind(target, target_type=None):
    normalized_target_type = str(target_type or "").strip().lower()
    if "ip" in normalized_target_type:
        return "ip"
    if any(token in normalized_target_type for token in ("domain", "\u57DF\u540D")):
        return "domain"

    target_text = str(target or "").strip()
    if not target_text:
        return "unknown"
    try:
        ipaddress.ip_address(target_text)
        return "ip"
    except ValueError:
        if "." in target_text:
            return "domain"
    return "other"


def detect_candidate_matches(row_or_value):
    matches = []
    for rule in DEFAULT_CANDIDATE_RULES:
        if _field_matches_rule(_extract_field_value(row_or_value, rule["field"]), rule):
            matches.append(rule)
    return matches


def is_candidate_alert(row_or_value):
    return bool(detect_candidate_matches(row_or_value))


def build_candidate_reason_labels(
    row_dict,
    matches,
    heat=None,
    trace_info=None,
    event_info=None,
    device_tags=None,
):
    reasons = [rule["label"] for rule in matches]
    threat_level = str(row_dict.get("threat_level") or "").strip()
    if threat_level:
        reasons.append(f"\u5a01\u80c1\u7b49\u7ea7:{threat_level}")
    if row_dict.get("apt_org_tier"):
        reasons.append(f"APT \u5206\u7ea7:{row_dict['apt_org_tier']}")
    vendor_count = len(split_multi_values(row_dict.get("vendors")))
    if vendor_count >= 2:
        reasons.append(f"\u591a\u5382\u5546\u540c\u65f6\u547d\u4e2d({vendor_count})")
    heat = heat or {}
    target_alert_count = int(heat.get("target_alert_count") or 0)
    target_device_count = int(heat.get("target_device_count") or 0)
    source_ip_alert_count = int(heat.get("source_ip_alert_count") or 0)
    device_alert_count = int(heat.get("device_alert_count") or 0)
    if target_device_count >= 2:
        reasons.append(f"\u540c\u76ee\u6807\u6d89\u53ca {target_device_count} \u53f0\u8bbe\u5907")
    if target_alert_count >= 2:
        reasons.append(f"\u76ee\u6807\u70ed\u5ea6:{target_alert_count} \u6761")
    if source_ip_alert_count >= 2:
        reasons.append(f"\u6e90 IP \u70ed\u5ea6:{source_ip_alert_count} \u6761")
    if device_alert_count >= 2:
        reasons.append(f"\u8bbe\u5907\u70ed\u5ea6:{device_alert_count} \u6761")
    if trace_info:
        note_preview = trace_info.get("note", "")
        reasons.append(f"IOC\u5907\u6ce8:{note_preview}" if note_preview else "IOC\u5907\u6ce8:\u6709\u8bb0\u5f55")
    if event_info:
        reasons.append(f"\u5df2\u5173\u8054\u4e8b\u4ef6:{event_info.get('event_name')}")
    if device_tags:
        preview = ",".join(tag["name"] for tag in device_tags[:3])
        reasons.append(f"\u8bbe\u5907\u6807\u7b7e:{preview}")
    deduped = []
    seen = set()
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        deduped.append(reason)
    return deduped


def compute_candidate_score(row_dict, matches, heat, trace_info=None, event_info=None, device_tags=None):
    score = sum(int(rule.get("score") or 0) for rule in matches)
    score += _threat_level_score(row_dict.get("threat_level"))
    score += _tier_score(row_dict.get("apt_org_tier"))

    score += min(int(heat.get("target_alert_count") or 0) * 2, 18)
    score += min(int(heat.get("target_device_count") or 0) * 6, 24)
    score += min(int(heat.get("source_ip_alert_count") or 0) * 2, 14)
    score += min(int(heat.get("device_alert_count") or 0), 10)

    vendor_count = len(split_multi_values(row_dict.get("vendors")))
    if vendor_count >= 2:
        score += min(vendor_count * 3, 9)

    if trace_info and trace_info.get("active"):
        score -= 12
    elif trace_info:
        score -= 4
    if event_info:
        score += 6
    if device_tags:
        score += min(len(device_tags) * 2, 8)
    return score


def classify_candidate_priority(score):
    if score >= 110:
        return {"id": "p1", "label": "\u9ad8\u4f18\u5148", "rank": 3}
    if score >= 75:
        return {"id": "p2", "label": "\u4e2d\u4f18\u5148", "rank": 2}
    return {"id": "p3", "label": "\u89c2\u5bdf", "rank": 1}


def compute_alert_content_hash(payload):
    normalized = {}
    for field in ALERT_CONTENT_FIELDS:
        value = payload.get(field)
        if isinstance(value, str):
            value = value.strip()
        normalized[field] = value
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
