from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from backend.utils.db import get_db


router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("")
def list_devices(
    keyword: str = Query(None),
    tags: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    db=Depends(get_db),
):
    conditions = []
    params = {}

    if keyword:
        conditions.append("(a.device_id LIKE :kw OR a.source_ip LIKE :kw)")
        params["kw"] = f"%{keyword}%"

    tag_ids = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    if tag_ids:
        placeholders = ", ".join(f":tag_{i}" for i in range(len(tag_ids)))
        conditions.append(
            "EXISTS ("
            "  SELECT 1 FROM device_tags dt "
            f"  WHERE dt.device_id = a.device_id AND dt.tag_id IN ({placeholders})"
            ")"
        )
        for i, tag_id in enumerate(tag_ids):
            params[f"tag_{i}"] = tag_id

    where = " AND ".join(conditions) if conditions else "1=1"
    total = db.execute(text(f"""
        SELECT COUNT(*) FROM (
          SELECT a.device_id FROM alerts a WHERE {where} GROUP BY a.device_id
        )
    """), params).scalar() or 0

    query_params = dict(params)
    query_params["limit"] = page_size
    query_params["offset"] = (page - 1) * page_size
    rows = db.execute(text(f"""
        SELECT
          a.device_id,
          MAX(a.source_ip) AS source_ip,
          SUM(CASE WHEN a.first_alert_time >= datetime('now', '-7 days') THEN 1 ELSE 0 END) AS alert_count_7d,
          MAX(a.last_alert_time) AS last_seen
        FROM alerts a
        WHERE {where}
        GROUP BY a.device_id
        ORDER BY last_seen DESC
        LIMIT :limit OFFSET :offset
    """), query_params).fetchall()

    items = [dict(row._mapping) for row in rows]
    device_ids = [item["device_id"] for item in items]
    tag_map = {device_id: [] for device_id in device_ids}
    if device_ids:
        placeholders = ", ".join(f":d_{i}" for i in range(len(device_ids)))
        tag_rows = db.execute(text(f"""
            SELECT dt.device_id, t.id, t.name, t.color, t.is_permanent, t.batch_id
            FROM device_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE dt.device_id IN ({placeholders})
            ORDER BY t.created_at DESC
        """), {f"d_{i}": device_id for i, device_id in enumerate(device_ids)}).fetchall()
        for row in tag_rows:
            tag_map[row[0]].append({
                "id": row[1],
                "name": row[2],
                "color": row[3],
                "is_permanent": row[4],
                "batch_id": row[5],
            })

    for item in items:
        item["tags"] = tag_map.get(item["device_id"], [])
        item["alert_count"] = item.pop("alert_count_7d") or 0
        if item.get("last_seen"):
            item["last_seen"] = str(item["last_seen"])

    return {"items": items, "total": total, "page": page, "page_size": page_size}
