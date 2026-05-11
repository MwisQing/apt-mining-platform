import re
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Any
from sqlalchemy import text
from datetime import datetime
from backend.utils.db import get_db, write_audit


router = APIRouter(prefix="/api/events", tags=["events"])


def _invalidate_candidate_cache():
    """Clear the in-process candidate cache so workbench sees updated event data."""
    try:
        from backend.api import alerts
        alerts._candidate_cache.clear()
    except Exception:
        pass


_PORT_SEP_RE = re.compile(r'[:：](\d{1,5})$')

# Common device ID prefixes seen in enterprise environments
_DEVICE_ID_PREFIXES = (
    'LAPTOP', 'DESKTOP', 'SRV', 'PC', 'WIN', 'NB', 'WS', 'HOST',
    'SERVER', 'WORKSTATION', 'MOBILE', 'TABLET', 'IOT', 'VM',
)
_DEVICE_ID_MARKER_RE = re.compile(
    r'(?:设备(?:[ \t]*[iI][dD])?|device[ \t_]*id)\s*[:：]?\s*',
    re.IGNORECASE,
)
_DEVICE_ID_STOP_RE = re.compile(r'\b(?:md5|sha1|sha-1)\b', re.IGNORECASE)
_HEX_WORD_RE = re.compile(r'\b[0-9A-Fa-f]{8,64}\b')


def _parse_target_port(raw: str) -> tuple:
    """Split target and port using English or Chinese colon. Returns (target, port)."""
    raw = raw.strip()
    m = _PORT_SEP_RE.search(raw)
    if m:
        target = raw[:m.start()].strip()
        port = m.group(1)
        return target, port
    return raw, ""


def _ordered_unique_upper(values):
    seen = set()
    ordered = []
    for value in values:
        normalized = (value or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _extract_device_hashes(text: str):
    devices = []
    lines = text.splitlines()
    line_starts = []
    position = 0
    for line in lines:
        line_starts.append(position)
        position += len(line) + 1

    for marker_match in _DEVICE_ID_MARKER_RE.finditer(text):
        line_index = text[:marker_match.start()].count('\n')
        start_offset = marker_match.end() - line_starts[line_index]

        for index in range(line_index, len(lines)):
            line = lines[index]
            segment = line[start_offset:] if index == line_index else line
            if _DEVICE_ID_STOP_RE.search(segment):
                break
            if not segment.strip():
                if index == line_index:
                    continue
                break
            devices.extend(_HEX_WORD_RE.findall(segment))
    return devices


def extract_iocs_from_text(text: str) -> dict:
    """Extract IPs (with optional port via : or ：), domains, and device IDs from free text.
    Does NOT extract MD5 hashes or file paths."""
    # Normalize Chinese colons to English for parsing
    normalized = text.replace('：', ':')

    # IPs with optional port
    ip_pattern = r'\b((?:\d{1,3}\.){3}\d{1,3})([:：]\d{1,5})?\b'
    ip_matches = re.findall(ip_pattern, normalized)
    # Also catch redacted IPs (at least one digit required)
    redacted_ip_pattern = r'\b([a-zA-Z0-9]{1,3}\.[a-zA-Z0-9]{1,3}\.[a-zA-Z0-9]{1,3}\.[a-zA-Z0-9]{1,3})([:：]\d{1,5})?\b'
    redacted_ip_matches = re.findall(redacted_ip_pattern, normalized)

    all_ip_matches = ip_matches + redacted_ip_matches
    ips = []
    for ip, port in all_ip_matches:
        if not re.search(r'\d', ip):
            continue
        if re.match(r'^[a-zA-Z]+\.[a-zA-Z]+\.[a-zA-Z]+\.[a-zA-Z]+$', ip):
            continue
        ips.append((ip, port.lstrip(':：') if port else ""))

    # URLs
    urls = list(set(re.findall(r'https?://[^\s,;，；\n]+', text)))

    # Domains with optional port (both : and ：), optional network:/domain:/dns: prefix
    domain_matches = re.findall(
        r'(?:network:|domain:|dns:)?'
        r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-xX]{0,61}[a-zA-Z0-9])?'
        r'\.)+[a-zA-Z]{2,}(?:[:：]\d{1,5})?',
        text
    )
    _EXEC_EXTENSIONS = {'exe', 'dll', 'sys', 'bat', 'cmd', 'scr', 'pif',
                        'vbs', 'ps1', 'msi', 'bin', 'dat', 'tmp'}
    domain_matches = [d for d in domain_matches if not (
        d.rsplit('.', 1)[-1].lower() in _EXEC_EXTENSIONS
        and not d.startswith(('network:', 'domain:', 'dns:', 'http'))
    )]

    devices = _extract_device_hashes(text)

    # 2. Prefix-based device IDs (LAPTOP-xxx, DESKTOP-xxx, etc.)
    device_prefix_pattern = '|'.join(_DEVICE_ID_PREFIXES)
    device_re = re.compile(rf'\b((?:{device_prefix_pattern})-[a-zA-Z0-9\-_]+)\b', re.IGNORECASE)
    devices.extend(m[0] for m in device_re.finditer(text))

    # 3. GUID-format (always safe — unique dash pattern)
    guid_re = re.compile(r'\b([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})\b')
    devices.extend(m[0] for m in guid_re.finditer(text))

    devices = _ordered_unique_upper(devices)

    # Build IOCs list (IPs + domains/URLs only, no MD5, no paths)
    iocs = []
    seen = set()

    for ip, port in ips:
        entry = {"target": ip, "port": port, "type": "ip"}
        key = (entry["target"], entry["port"])
        if key not in seen:
            seen.add(key)
            iocs.append(entry)

    for d in domain_matches:
        # Check if domain is the exact hostname of any URL (not just substring)
        url_hostnames = set()
        for u in urls:
            m_url = re.match(r'https?://([^/:]+)', u)
            if m_url:
                url_hostnames.add(m_url.group(1).lower())
        if d.lower() in url_hostnames:
            continue
        target, port = _parse_target_port(d)
        for prefix in ('network:', 'domain:', 'dns:'):
            if target.startswith(prefix):
                target = target[len(prefix):]
        if re.match(r'^(?:\d{1,3}\.){3}\d{1,3}$', target):
            continue
        if target.rsplit('.', 1)[-1].lower() in _EXEC_EXTENSIONS:
            continue
        entry = {"target": target, "port": port, "type": "domain"}
        key = (entry["target"], entry["port"])
        if key not in seen:
            seen.add(key)
            iocs.append(entry)

    for url in urls:
        entry = {"target": url, "port": "", "type": "url"}
        key = (entry["target"], entry["port"])
        if key not in seen:
            seen.add(key)
            iocs.append(entry)

    return {
        "iocs": iocs,
        "devices": devices,
    }


@router.post("/extract-iocs")
def extract_iocs(data: dict = Body(...)):
    """Extract IOCs (IPs/domains/URLs only, no MD5/path) and device IDs from event note text."""
    text = data.get("text", "")
    if not text:
        return {"iocs": [], "devices": []}
    return extract_iocs_from_text(text)


@router.get("")
def list_events(status: str = None, db=Depends(get_db)):
    sql = "SELECT * FROM mined_events"
    params = {}
    if status:
        sql += " WHERE status = :status"
        params["status"] = status
    sql += " ORDER BY mined_at DESC"
    rows = db.execute(text(sql), params).fetchall()
    items = []
    for r in rows:
        d = dict(r._mapping)
        for k in ("mined_at",):
            if k in d and d[k]:
                d[k] = str(d[k])
        items.append(d)
    return items


@router.post("")
def create_event(data: Any = Body(...), db=Depends(get_db)):
    now = datetime.now().isoformat()
    event_name = data.get("event_name", "")
    color = data.get("color", "#FF5722")
    status = data.get("status", "active")
    note = data.get("note", "")
    devices = data.get("devices", [])
    iocs = data.get("iocs", [])
    tag_devices = data.get("tag_devices", True)  # Auto-tag devices with event info

    cursor = db.execute(text(
        "INSERT INTO mined_events (event_name, color, status, mined_at, note) "
        "VALUES (:name, :color, :status, :mined_at, :note)"
    ), {"name": event_name, "color": color, "status": status, "mined_at": now, "note": note})
    event_id = cursor.lastrowid

    for did in devices:
        db.execute(text(
            "INSERT OR IGNORE INTO mined_event_devices (event_id, device_id) VALUES (:eid, :did)"
        ), {"eid": event_id, "did": did})

    for ioc in iocs:
        db.execute(text(
            "INSERT OR IGNORE INTO mined_event_iocs (event_id, target, port) VALUES (:eid, :target, :port)"
        ), {"eid": event_id, "target": ioc.get("target"), "port": ioc.get("port")})

    db.execute(text(
        "INSERT INTO event_followups (event_id, action_type, created_at, note) "
        "VALUES (:eid, 'note', :created_at, :note)"
    ), {"eid": event_id, "created_at": now, "note": f"创建事件: {event_name}"})

    # Auto-tag devices with event mining info
    if tag_devices and devices:
        tag_name = f"事件挖掘: {event_name}".strip()
        tag_row = db.execute(
            text("SELECT id FROM tags WHERE name = :name AND is_permanent = 1 ORDER BY id LIMIT 1"),
            {"name": tag_name}
        ).fetchone()
        if tag_row:
            tag_id = tag_row[0]
        else:
            tag_cursor = db.execute(text(
                "INSERT INTO tags (name, color, is_permanent, batch_id, created_at) "
                "VALUES (:name, :color, 1, NULL, :created_at)"
            ), {"name": tag_name, "color": color, "created_at": now})
            tag_id = tag_cursor.lastrowid

        for did in devices:
            db.execute(text(
                "INSERT OR IGNORE INTO device_tags (device_id, tag_id, created_at) "
                "VALUES (:did, :tid, :created_at)"
            ), {"did": did, "tid": tag_id, "created_at": now})

    write_audit(db, "create_event", "event", event_id, {
        "event_name": event_name,
        "device_count": len(devices),
        "ioc_count": len(iocs),
        "tagged_devices": len(devices) if tag_devices else 0,
    })
    db.commit()
    _invalidate_candidate_cache()
    return {"id": event_id}


@router.get("/{event_id}")
def get_event(event_id: int, db=Depends(get_db)):
    row = db.execute(text("SELECT * FROM mined_events WHERE id = :id"), {"id": event_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    d = dict(row._mapping)
    for k in ("mined_at",):
        if k in d and d[k]:
            d[k] = str(d[k])

    d["devices"] = [r[0] for r in db.execute(text(
        "SELECT device_id FROM mined_event_devices WHERE event_id = :eid"
    ), {"eid": event_id}).fetchall()]

    d["iocs"] = [dict(r._mapping) for r in db.execute(text(
        "SELECT target, port FROM mined_event_iocs WHERE event_id = :eid ORDER BY target, port"
    ), {"eid": event_id}).fetchall()]

    d["followups"] = []
    for f in db.execute(text(
        "SELECT * FROM event_followups WHERE event_id = :eid ORDER BY created_at DESC"
    ), {"eid": event_id}).fetchall():
        fd = dict(f._mapping)
        if fd.get("created_at"):
            fd["created_at"] = str(fd["created_at"])
        d["followups"].append(fd)

    return d


@router.patch("/{event_id}")
def update_event(event_id: int, data: Any = Body(...), db=Depends(get_db)):
    row = db.execute(text("SELECT * FROM mined_events WHERE id = :id"), {"id": event_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    updates = []
    params = {"id": event_id}
    for field in ("event_name", "color", "note"):
        if field in data:
            updates.append(f"{field} = :{field}")
            params[field] = data[field]
    if "status" in data:
        updates.append("status = :status")
        params["status"] = data["status"]
        now = datetime.now().isoformat()
        db.execute(text(
            "INSERT INTO event_followups (event_id, action_type, created_at, note) "
            "VALUES (:eid, 'status_change', :created_at, :note)"
        ), {"eid": event_id, "created_at": now, "note": f"状态变更为: {data['status']}"})

    if updates:
        db.execute(text(f"UPDATE mined_events SET {', '.join(updates)} WHERE id = :id"), params)
        write_audit(db, "update_event", "event", event_id, data)
        db.commit()
        _invalidate_candidate_cache()
    return {"ok": True}


@router.delete("/{event_id}")
def delete_event(event_id: int, db=Depends(get_db)):
    db.execute(text("DELETE FROM mined_events WHERE id = :id"), {"id": event_id})
    write_audit(db, "delete_event", "event", event_id)
    db.commit()
    _invalidate_candidate_cache()
    return {"ok": True}


@router.post("/{event_id}/followups")
def add_followup(event_id: int, data: Any = Body(...), db=Depends(get_db)):
    row = db.execute(text("SELECT * FROM mined_events WHERE id = :id"), {"id": event_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    now = datetime.now().isoformat()
    db.execute(text(
        "INSERT INTO event_followups (event_id, action_type, created_at, note) "
        "VALUES (:eid, :action_type, :created_at, :note)"
    ), {"eid": event_id, "action_type": data.get("action_type", "note"), "created_at": now, "note": data.get("note", "")})
    write_audit(db, "add_event_followup", "event", event_id, data)
    db.commit()
    return {"ok": True}


@router.post("/{event_id}/devices")
def add_devices(event_id: int, data: Any = Body(...), db=Depends(get_db)):
    devices = data.get("devices", [])
    for did in devices:
        db.execute(text(
            "INSERT OR IGNORE INTO mined_event_devices (event_id, device_id) VALUES (:eid, :did)"
        ), {"eid": event_id, "did": did})
    write_audit(db, "add_event_devices", "event", event_id, {"devices": devices})
    db.commit()
    return {"ok": True}


@router.post("/{event_id}/iocs")
def add_iocs(event_id: int, data: Any = Body(...), db=Depends(get_db)):
    iocs = data.get("iocs", [])
    for ioc in iocs:
        db.execute(text(
            "INSERT OR IGNORE INTO mined_event_iocs (event_id, target, port) VALUES (:eid, :target, :port)"
        ), {"eid": event_id, "target": ioc.get("target"), "port": ioc.get("port")})
    write_audit(db, "add_event_iocs", "event", event_id, {"iocs": iocs})
    db.commit()
    return {"ok": True}


@router.delete("/{event_id}/devices/{device_id}")
def remove_device(event_id: int, device_id: str, db=Depends(get_db)):
    db.execute(text(
        "DELETE FROM mined_event_devices WHERE event_id = :eid AND device_id = :did"
    ), {"eid": event_id, "did": device_id})
    write_audit(db, "remove_event_device", "event", event_id, {"device_id": device_id})
    db.commit()
    return {"ok": True}


@router.delete("/{event_id}/iocs")
def remove_ioc(event_id: int, target: str = Query(...), port: str = Query(None), db=Depends(get_db)):
    db.execute(text(
        "DELETE FROM mined_event_iocs "
        "WHERE event_id = :eid AND target = :target AND COALESCE(port, '') = COALESCE(:port, '')"
    ), {"eid": event_id, "target": target, "port": port or ""})
    write_audit(db, "remove_event_ioc", "event", event_id, {"target": target, "port": port})
    db.commit()
    return {"ok": True}
