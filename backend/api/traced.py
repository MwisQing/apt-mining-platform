from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File
from typing import Any
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import pandas as pd
from backend.utils.db import get_db, write_audit


router = APIRouter(prefix="/api/traced", tags=["traced"])


def _first_existing(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _clean_cell(value):
    if pd.isna(value):
        return None
    text_value = str(value).strip()
    if not text_value or text_value.lower() == "nan":
        return None
    return text_value


def _parse_date(value):
    text_value = _clean_cell(value)
    if not text_value:
        return None
    parsed = pd.to_datetime(
        text_value.replace("/", "-").replace(".", "-"),
        errors="coerce",
    )
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().isoformat()


def _normalize_traced_item(item, *, now=None):
    payload = dict(item or {})
    target = str(payload.get("target") or "").strip()
    if not target:
        return None
    port = payload.get("port")
    port = None if port is None else str(port).strip()
    note = payload.get("note")
    return {
        "target": target,
        "port": port or None,
        "traced_at": payload.get("traced_at") or now,
        "note": "" if note is None else str(note),
    }


def _invalidate_candidate_cache():
    try:
        from backend.api import alerts
        alerts._candidate_cache.clear()
        alerts._invalidate_full_cache()
    except Exception:
        pass


@router.get("")
def list_traced(keyword: str = None, db=Depends(get_db)):
    params = {}
    where = "1=1"
    if keyword:
        where = "(target LIKE :kw OR note LIKE :kw2)"
        params["kw"] = f"%{keyword}%"
        params["kw2"] = f"%{keyword}%"
    rows = db.execute(text(f"SELECT * FROM traced_targets WHERE {where} ORDER BY traced_at DESC"), params).fetchall()
    items = []
    for r in rows:
        d = dict(r._mapping)
        if d.get("traced_at"):
            d["traced_at"] = str(d["traced_at"])
        items.append(d)
    return items


@router.post("")
def create_traced(data: Any = Body(...), db=Depends(get_db)):
    now = datetime.now().isoformat()
    items = data if isinstance(data, list) else [data]
    ids = []
    for item in items:
        normalized = _normalize_traced_item(item, now=now)
        if not normalized:
            continue
        target = normalized["target"]
        port = normalized["port"]
        note = normalized["note"]
        traced_at = normalized["traced_at"]
        existing = db.execute(text(
            "SELECT id FROM traced_targets WHERE target = :target AND COALESCE(port, '') = COALESCE(:port, '')"
        ), {"target": target, "port": port or ""}).fetchone()
        if existing:
            continue
        cursor = db.execute(text(
            "INSERT INTO traced_targets (target, port, traced_at, note) "
            "VALUES (:target, :port, :traced_at, :note)"
        ), {"target": target, "port": port or None, "traced_at": traced_at, "note": note})
        if cursor.lastrowid:
            ids.append(cursor.lastrowid)
    if ids:
        write_audit(db, "create_traced", "traced_target", ",".join(str(i) for i in ids), {"count": len(ids)})
    db.commit()
    _invalidate_candidate_cache()
    return {"ids": ids, "count": len(ids)}


@router.post("/import")
async def import_traced(file: UploadFile = File(...), db=Depends(get_db)):
    df = pd.read_excel(file.file)
    if df.empty:
        return {"inserted": 0, "skipped": 0, "failed": 0, "failures": []}

    columns = list(df.columns)
    target_col = _first_existing(columns, ["外联目标", "目标", "target", "Target", "域名", "IP", "目标IP/域名"])
    port_col = _first_existing(columns, ["外联端口", "端口", "port", "Port"])
    date_col = _first_existing(columns, ["追踪日期", "追踪时间", "traced_at", "日期", "时间"])
    note_col = _first_existing(columns, ["备注", "note", "Note", "说明"])
    if not target_col:
        target_col = columns[0]

    inserted = 0
    skipped = 0
    failed = 0
    failures = []
    ids = []

    for idx, row in df.iterrows():
        try:
            target = _clean_cell(row[target_col])
            if not target:
                skipped += 1
                continue
            port = _clean_cell(row[port_col]) if port_col else None
            traced_at = _parse_date(row[date_col]) if date_col else None
            note = _clean_cell(row[note_col]) if note_col else ""
            existing = db.execute(text(
                "SELECT id FROM traced_targets WHERE target = :target AND COALESCE(port, '') = COALESCE(:port, '')"
            ), {"target": target, "port": port or ""}).fetchone()
            if existing:
                skipped += 1
                continue
            result = db.execute(text(
                "INSERT INTO traced_targets (target, port, traced_at, note) "
                "VALUES (:target, :port, :traced_at, :note)"
            ), {
                "target": target,
                "port": port,
                "traced_at": traced_at,
                "note": note or "",
            })
            if result.rowcount:
                inserted += 1
                if result.lastrowid:
                    ids.append(result.lastrowid)
            else:
                skipped += 1
        except Exception as e:
            failed += 1
            failures.append({"row": int(idx) + 2, "error": str(e)})

    write_audit(db, "import_traced", "traced_target", ",".join(str(i) for i in ids), {
        "source_file": file.filename,
        "inserted": inserted,
        "skipped": skipped,
        "failed": failed,
    })
    db.commit()
    if inserted or skipped:
        _invalidate_candidate_cache()
    return {"inserted": inserted, "skipped": skipped, "failed": failed, "failures": failures}


@router.patch("/{traced_id}")
def update_traced(traced_id: int, data: Any = Body(...), db=Depends(get_db)):
    current = db.execute(text(
        "SELECT * FROM traced_targets WHERE id = :id"
    ), {"id": traced_id}).fetchone()
    if not current:
        raise HTTPException(status_code=404, detail="Traced target not found")

    current_map = dict(current._mapping)
    normalized = _normalize_traced_item({
        "target": data.get("target", current_map.get("target")),
        "port": data.get("port", current_map.get("port")),
        "traced_at": data.get("traced_at", current_map.get("traced_at")),
        "note": data.get("note", current_map.get("note")),
    })
    if not normalized:
        raise HTTPException(status_code=400, detail="target is required")

    duplicate = db.execute(text(
        "SELECT id FROM traced_targets "
        "WHERE id != :id AND target = :target AND COALESCE(port, '') = COALESCE(:port, '')"
    ), {
        "id": traced_id,
        "target": normalized["target"],
        "port": normalized["port"] or "",
    }).fetchone()
    if duplicate:
        raise HTTPException(status_code=409, detail="同样的 IOC 备注已存在")

    updates = []
    params = {"id": traced_id}
    for field in ("target", "port", "note", "traced_at"):
        if field in data:
            updates.append(f"{field} = :{field}")
            params[field] = normalized[field]
    if updates:
        try:
            db.execute(text(f"UPDATE traced_targets SET {', '.join(updates)} WHERE id = :id"), params)
            write_audit(db, "update_traced", "traced_target", traced_id, {
                field: params[field] for field in ("target", "port", "note", "traced_at") if field in params
            })
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="同样的 IOC 备注已存在")
        _invalidate_candidate_cache()
    return {"ok": True}


@router.delete("/{traced_id}")
def delete_traced(traced_id: int, db=Depends(get_db)):
    db.execute(text("DELETE FROM traced_targets WHERE id = :id"), {"id": traced_id})
    write_audit(db, "delete_traced", "traced_target", traced_id)
    db.commit()
    _invalidate_candidate_cache()
    return {"ok": True}
