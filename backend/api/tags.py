from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File
from typing import Any
from sqlalchemy import text
from datetime import datetime
import json
from backend.utils.db import get_db, write_audit
from backend.services.snapshot_builder import request_snapshot_refresh


router = APIRouter(prefix="/api/tags", tags=["tags"])


def _invalidate_candidate_cache():
    """Clear the in-process candidate cache so workbench sees updated tag data."""
    try:
        from backend.api import alerts
        alerts._candidate_cache.clear()
        alerts._invalidate_full_cache()
    except Exception:
        pass
    try:
        request_snapshot_refresh("tags")
    except Exception:
        pass

TXT_TAG_IMPORT_PRESETS = (
    {
        "match_tokens": ("01.", "排查成功", "查实成功"),
        "tag_name": "排查成功",
        "color": "#67C23A",
    },
    {
        "match_tokens": ("02.", "重点设备"),
        "tag_name": "重点设备",
        "color": "#F56C6C",
    },
    {
        "match_tokens": ("03.", "不好查", "不好排查"),
        "tag_name": "不好查",
        "color": "#909399",
    },
)


def _clean_device_ids(devices):
    result = []
    seen = set()
    for device_id in devices or []:
        normalized = str(device_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _create_tag_batch(db, *, batch_name, note, tag_name, color, devices, source_file=None):
    now = datetime.now().isoformat()
    devices = _clean_device_ids(devices)
    tag_name = tag_name.strip() if tag_name else ""
    if not tag_name or not devices:
        raise HTTPException(status_code=400, detail="tag_name and devices are required")

    note_parts = [part for part in [note, f"source_file={source_file}" if source_file else None] if part]
    batch_note = " | ".join(note_parts)

    cursor = db.execute(text(
        "INSERT INTO tag_batches (batch_name, created_at, note, status, device_ids_snapshot) "
        "VALUES (:name, :created_at, :note, 'active', :device_ids_snapshot)"
    ), {
        "name": batch_name,
        "created_at": now,
        "note": batch_note,
        "device_ids_snapshot": json.dumps(devices, ensure_ascii=False),
    })
    batch_id = cursor.lastrowid

    cursor = db.execute(text(
        "INSERT INTO tags (name, color, is_permanent, batch_id, created_at, note) "
        "VALUES (:name, :color, 0, :batch_id, :created_at, :note)"
    ), {"name": tag_name, "color": color, "batch_id": batch_id, "created_at": now, "note": batch_note})
    tag_id = cursor.lastrowid

    for did in devices:
        db.execute(text(
            "INSERT OR IGNORE INTO device_tags (device_id, tag_id, created_at) "
            "VALUES (:did, :tid, :created_at)"
        ), {"did": did, "tid": tag_id, "created_at": now})

    write_audit(db, "create_tag_batch", "tag_batch", batch_id, {
        "tag_name": tag_name,
        "tag_color": color,
        "devices": devices,
        "device_count": len(devices),
        "source_file": source_file,
    })
    return {"batch_id": batch_id, "tag_id": tag_id, "device_count": len(devices)}


def _parse_device_snapshot(snapshot_text):
    if not snapshot_text:
        return []
    try:
        data = json.loads(snapshot_text)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return _clean_device_ids(data)


def _resolve_batch_device_ids(db, batch_id: int, batch_row=None):
    batch = batch_row
    if batch is None:
        batch = db.execute(text(
            "SELECT * FROM tag_batches WHERE id = :id"
        ), {"id": batch_id}).fetchone()
    if not batch:
        return []

    batch_map = dict(batch._mapping)
    device_ids = _parse_device_snapshot(batch_map.get("device_ids_snapshot"))
    if device_ids:
        return device_ids

    audit_row = db.execute(text(
        "SELECT detail FROM audit_log WHERE action = 'create_tag_batch' AND target_id = :tid "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"tid": str(batch_id)}).fetchone()
    if audit_row and audit_row[0]:
        try:
            detail = json.loads(audit_row[0])
        except ValueError:
            detail = {}
        device_ids = _clean_device_ids(detail.get("devices", []))
        if device_ids:
            db.execute(text(
                "UPDATE tag_batches SET device_ids_snapshot = :snapshot WHERE id = :id"
            ), {"id": batch_id, "snapshot": json.dumps(device_ids, ensure_ascii=False)})
            return device_ids

    device_rows = db.execute(text(
        "SELECT DISTINCT dt.device_id FROM device_tags dt "
        "JOIN tags t ON t.id = dt.tag_id "
        "WHERE t.batch_id = :id ORDER BY dt.device_id"
    ), {"id": batch_id}).fetchall()
    device_ids = _clean_device_ids([row[0] for row in device_rows])
    if device_ids:
        db.execute(text(
            "UPDATE tag_batches SET device_ids_snapshot = :snapshot WHERE id = :id"
        ), {"id": batch_id, "snapshot": json.dumps(device_ids, ensure_ascii=False)})
    return device_ids


def _resolve_txt_import_preset(filename):
    lowered = str(filename or "").lower()
    for preset in TXT_TAG_IMPORT_PRESETS:
        if any(token.lower() in lowered for token in preset["match_tokens"]):
            return preset
    return {
        "tag_name": str(filename or "导入标签").rsplit(".", 1)[0] or "导入标签",
        "color": "#409EFF",
    }


async def _read_text_upload(file: UploadFile):
    content = await file.read()
    await file.close()
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


@router.get("")
def list_tags(db=Depends(get_db)):
    rows = db.execute(text("SELECT * FROM tags ORDER BY created_at DESC")).fetchall()
    return [dict(r._mapping) for r in rows]


@router.patch("/tags/{tag_id}")
def update_tag(tag_id: int, data: Any = Body(...), db=Depends(get_db)):
    """Update tag name and/or color. Body: { name?, color? }"""
    tag = db.execute(text("SELECT id FROM tags WHERE id = :id"), {"id": tag_id}).fetchone()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    updates = []
    params = {"id": tag_id}
    if "name" in data:
        new_name = (data["name"] or "").strip()
        if new_name:
            updates.append("name = :name")
            params["name"] = new_name
    if "color" in data:
        updates.append("color = :color")
        params["color"] = data["color"]
    if updates:
        db.execute(text(f"UPDATE tags SET {', '.join(updates)} WHERE id = :id"), params)
        write_audit(db, "update_tag", "tag", tag_id, {k: params.get(k) for k in ("name", "color") if k in params})
        db.commit()
        _invalidate_candidate_cache()
    return {"ok": True}


@router.get("/batches")
def list_batches(db=Depends(get_db)):
    rows = db.execute(text(
        "SELECT tb.id, tb.batch_name, tb.created_at, tb.note, tb.status, "
        "COALESCE((SELECT t.name FROM tags t WHERE t.batch_id = tb.id ORDER BY t.id LIMIT 1), '') as tag_name, "
        "COALESCE((SELECT t.color FROM tags t WHERE t.batch_id = tb.id ORDER BY t.id LIMIT 1), '#409EFF') as color, "
        "GROUP_CONCAT(DISTINCT t2.name) as tag_names, "
        "COUNT(DISTINCT dt.device_id) as device_count "
        "FROM tag_batches tb "
        "LEFT JOIN tags t2 ON t2.batch_id = tb.id "
        "LEFT JOIN device_tags dt ON dt.tag_id = t2.id "
        "GROUP BY tb.id ORDER BY tb.created_at DESC"
    )).fetchall()
    items = []
    for r in rows:
        d = dict(r._mapping)
        if d.get("created_at"):
            d["created_at"] = str(d["created_at"])
        items.append(d)
    return items


@router.post("/batches")
def create_batch(data: Any = Body(...), db=Depends(get_db)):
    batch_name = data.get("batch_name", "")
    note = data.get("note", "")
    devices = data.get("devices", [])
    tag_name = data.get("tag_name", "")
    color = data.get("color", "#409EFF")
    result = _create_tag_batch(
        db,
        batch_name=batch_name,
        note=note,
        tag_name=tag_name,
        color=color,
        devices=devices,
    )
    db.commit()
    _invalidate_candidate_cache()
    return result


@router.post("/batches/import-text-files")
async def import_text_files(files: list[UploadFile] = File(...), db=Depends(get_db)):
    if not files:
        raise HTTPException(status_code=400, detail="files are required")

    imported = []
    skipped = []
    for file in files:
        text_content = await _read_text_upload(file)
        device_ids = _clean_device_ids(text_content.splitlines())
        if not device_ids:
            skipped.append({"source_file": file.filename, "reason": "empty_file"})
            continue

        preset = _resolve_txt_import_preset(file.filename)
        batch_name = f"{preset['tag_name']}批量导入"
        result = _create_tag_batch(
            db,
            batch_name=batch_name,
            note="txt批量导入",
            tag_name=preset["tag_name"],
            color=preset["color"],
            devices=device_ids,
            source_file=file.filename,
        )
        imported.append({
            "source_file": file.filename,
            "tag_name": preset["tag_name"],
            **result,
        })

    db.commit()
    _invalidate_candidate_cache()
    return {
        "imported": imported,
        "skipped": skipped,
        "count": len(imported),
    }


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, db=Depends(get_db)):
    """Get batch detail including device list."""
    batch = db.execute(text(
        "SELECT * FROM tag_batches WHERE id = :id"
    ), {"id": batch_id}).fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    bd = dict(batch._mapping)
    if bd.get("created_at"):
        bd["created_at"] = str(bd["created_at"])

    tag_rows = db.execute(text(
        "SELECT id, name, color, is_permanent FROM tags WHERE batch_id = :id"
    ), {"id": batch_id}).fetchall()
    bd["tags"] = [dict(r._mapping) for r in tag_rows]

    device_rows = db.execute(text(
        "SELECT DISTINCT dt.device_id FROM device_tags dt "
        "JOIN tags t ON t.id = dt.tag_id "
        "WHERE t.batch_id = :id ORDER BY dt.device_id"
    ), {"id": batch_id}).fetchall()
    bd["devices"] = [r[0] for r in device_rows]
    bd["device_count"] = len(bd["devices"])

    return bd


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: int, db=Depends(get_db)):
    """Soft-delete a batch: mark status='deleted', keep tags and device associations."""
    batch = db.execute(text(
        "SELECT id FROM tag_batches WHERE id = :id"
    ), {"id": batch_id}).fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    db.execute(text(
        "UPDATE tag_batches SET status = 'deleted' WHERE id = :id"
    ), {"id": batch_id})
    write_audit(db, "soft_delete_tag_batch", "tag_batch", batch_id, {})
    db.commit()
    _invalidate_candidate_cache()
    return {"ok": True}


@router.delete("/batches/{batch_id}/devices")
def remove_devices_from_batch(batch_id: int, data: Any = Body(...), db=Depends(get_db)):
    """Remove specific devices from a batch. Body: { devices: [...] }"""
    devices = _clean_device_ids(data.get("devices", []))
    if not devices:
        raise HTTPException(status_code=400, detail="devices required")

    tag_ids = [row[0] for row in db.execute(text(
        "SELECT id FROM tags WHERE batch_id = :id"
    ), {"id": batch_id}).fetchall()]
    if not tag_ids:
        raise HTTPException(status_code=404, detail="Batch has no tags")

    placeholders_d = ", ".join(f":d_{i}" for i in range(len(devices)))
    placeholders_t = ", ".join(f":t_{i}" for i in range(len(tag_ids)))
    params = {f"d_{i}": d for i, d in enumerate(devices)}
    params.update({f"t_{i}": t for i, t in enumerate(tag_ids)})
    result = db.execute(text(
        f"DELETE FROM device_tags WHERE device_id IN ({placeholders_d}) AND tag_id IN ({placeholders_t})"
    ), params)

    write_audit(db, "remove_devices_from_batch", "tag_batch", batch_id,
                {
                    "devices": devices,
                    "tag_ids": tag_ids,
                    "removed_count": result.rowcount,
                })
    db.commit()
    _invalidate_candidate_cache()
    return {"ok": True, "removed_count": result.rowcount}


@router.post("/batches/{batch_id}/restore")
def restore_batch(batch_id: int, db=Depends(get_db)):
    """Re-apply this batch's tags to devices. Reconstructs tags from audit log if deleted."""
    batch = db.execute(text(
        "SELECT * FROM tag_batches WHERE id = :id"
    ), {"id": batch_id}).fetchone()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    now = datetime.now().isoformat()

    # Find or recreate tags for this batch
    tag_rows = db.execute(text(
        "SELECT id, name, color FROM tags WHERE batch_id = :id"
    ), {"id": batch_id}).fetchall()

    if not tag_rows:
        # Reconstruct from audit log
        audit_row = db.execute(text(
            "SELECT detail FROM audit_log WHERE action = 'create_tag_batch' AND target_id = :tid "
            "ORDER BY created_at DESC LIMIT 1"
        ), {"tid": str(batch_id)}).fetchone()
        if not audit_row or not audit_row[0]:
            raise HTTPException(status_code=400, detail="No audit log to reconstruct from")

        detail = json.loads(audit_row[0]) if audit_row[0] else {}
        tag_name = (detail.get("tag_name") or "").strip()
        tag_color = detail.get("tag_color") or "#409EFF"
        if not tag_name:
            raise HTTPException(status_code=400, detail="Cannot determine tag name from audit log")

        cursor = db.execute(text(
            "INSERT INTO tags (name, color, is_permanent, batch_id, created_at) "
            "VALUES (:name, :color, 0, :batch_id, :created_at)"
        ), {"name": tag_name, "color": tag_color, "batch_id": batch_id, "created_at": now})
        tag_rows = [type('obj', (object,), {'id': cursor.lastrowid, 'name': tag_name, 'color': tag_color})]

    tag_ids = [getattr(r, 'id', r[0]) for r in tag_rows]
    devices = _resolve_batch_device_ids(db, batch_id, batch)
    if not devices:
        raise HTTPException(status_code=400, detail="No saved devices found for this batch")

    restored_count = 0
    for tag_row in tag_rows:
        tag_id = getattr(tag_row, 'id', tag_row[0])
        for device_id in devices:
            result = db.execute(text(
                "INSERT OR IGNORE INTO device_tags (device_id, tag_id, created_at) "
                "VALUES (:did, :tid, :created_at)"
            ), {"did": device_id, "tid": tag_id, "created_at": now})
            if result.rowcount:
                restored_count += 1

    # Reset batch status to active (in case it was soft-deleted)
    db.execute(text(
        "UPDATE tag_batches SET status = 'active' WHERE id = :id"
    ), {"id": batch_id})
    write_audit(db, "restore_batch", "tag_batch", batch_id,
                {"tag_ids": tag_ids, "devices": devices, "restored_count": restored_count})
    db.commit()
    _invalidate_candidate_cache()
    return {"ok": True, "restored_count": restored_count}


@router.get("/devices/{device_id}/tags")
def get_device_tags(device_id: str, db=Depends(get_db)):
    rows = db.execute(text(
        "SELECT t.* FROM tags t "
        "JOIN device_tags dt ON dt.tag_id = t.id "
        "WHERE dt.device_id = :did"
    ), {"did": device_id}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/devices/tags")
def add_device_tag(data: Any = Body(...), db=Depends(get_db)):
    now = datetime.now().isoformat()
    device_id = data.get("device_id")
    tag_name = (data.get("tag_name") or "").strip()
    color = data.get("color", "#409EFF")

    if not device_id or not tag_name:
        raise HTTPException(status_code=400, detail="device_id and tag_name required")

    row = db.execute(text("SELECT id FROM tags WHERE name = :name ORDER BY id LIMIT 1"), {"name": tag_name}).fetchone()
    if row:
        tag_id = row[0]
    else:
        cursor = db.execute(text(
            "INSERT INTO tags (name, color, is_permanent, batch_id, created_at) "
            "VALUES (:name, :color, 1, NULL, :created_at)"
        ), {"name": tag_name, "color": color, "created_at": now})
        tag_id = cursor.lastrowid

    db.execute(text(
        "INSERT OR IGNORE INTO device_tags (device_id, tag_id, created_at) "
        "VALUES (:did, :tid, :created_at)"
    ), {"did": device_id, "tid": tag_id, "created_at": now})
    write_audit(db, "add_device_tag", "device", device_id, {"tag_id": tag_id, "tag_name": tag_name})
    db.commit()
    _invalidate_candidate_cache()
    return {"tag_id": tag_id}


@router.delete("/devices/{device_id}/tags/{tag_id}")
def remove_device_tag(device_id: str, tag_id: int, db=Depends(get_db)):
    db.execute(text(
        "DELETE FROM device_tags WHERE device_id = :did AND tag_id = :tid"
    ), {"did": device_id, "tid": tag_id})
    write_audit(db, "remove_device_tag", "device", device_id, {"tag_id": tag_id})
    db.commit()
    _invalidate_candidate_cache()
    return {"ok": True}


@router.post("/devices/batch")
def batch_add_device_tag(data: Any = Body(...), db=Depends(get_db)):
    """Batch add a tag to multiple devices. Body: { devices: [...], tag_name, color?, record_batch? }
    When record_batch is true (default), creates a tag_batches record for history and undo support."""
    now = datetime.now().isoformat()
    devices = _clean_device_ids(data.get("devices", []))
    tag_name = (data.get("tag_name") or "").strip()
    color = data.get("color", "#409EFF")
    record_batch = data.get("record_batch", True)

    if not devices or not tag_name:
        raise HTTPException(status_code=400, detail="devices and tag_name required")

    if record_batch:
        batch_name = f"批量打标: {tag_name}"
        result = _create_tag_batch(
            db,
            batch_name=batch_name,
            note="手动批量打标",
            tag_name=tag_name,
            color=color,
            devices=devices,
        )
        db.commit()
        _invalidate_candidate_cache()
        return {**result, "tag_name": tag_name}

    # Legacy: permanent tag without batch record
    row = db.execute(text("SELECT id FROM tags WHERE name = :name ORDER BY id LIMIT 1"), {"name": tag_name}).fetchone()
    if row:
        tag_id = row[0]
    else:
        cursor = db.execute(text(
            "INSERT INTO tags (name, color, is_permanent, batch_id, created_at) "
            "VALUES (:name, :color, 1, NULL, :created_at)"
        ), {"name": tag_name, "color": color, "created_at": now})
        tag_id = cursor.lastrowid

    count = 0
    for did in devices:
        result = db.execute(text(
            "INSERT OR IGNORE INTO device_tags (device_id, tag_id, created_at) "
            "VALUES (:did, :tid, :created_at)"
        ), {"did": did, "tid": tag_id, "created_at": now})
        if result.rowcount:
            count += 1

    write_audit(db, "batch_add_device_tag", "device", None, {"tag_id": tag_id, "tag_name": tag_name, "device_count": count})
    db.commit()
    _invalidate_candidate_cache()
    return {"tag_id": tag_id, "tag_name": tag_name, "device_count": count}


@router.delete("/devices/batch")
def batch_remove_device_tag(data: Any = Body(...), db=Depends(get_db)):
    """Batch remove a tag from multiple devices. Body: { devices: [...], tag_id }"""
    devices = _clean_device_ids(data.get("devices", []))
    tag_id = data.get("tag_id")

    if not devices or not tag_id:
        raise HTTPException(status_code=400, detail="devices and tag_id required")

    placeholders = ", ".join(f":d_{i}" for i in range(len(devices)))
    params = {f"d_{i}": device_id for i, device_id in enumerate(devices)}
    params["tid"] = tag_id
    result = db.execute(text(
        f"DELETE FROM device_tags WHERE tag_id = :tid AND device_id IN ({placeholders})"
    ), params)

    write_audit(db, "batch_remove_device_tag", "device", None, {"tag_id": tag_id, "device_count": result.rowcount})
    db.commit()
    _invalidate_candidate_cache()
    return {"ok": True, "removed_count": result.rowcount}
