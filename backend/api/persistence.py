from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from backend.utils.db import get_db


router = APIRouter(prefix="/api/persistence", tags=["persistence"])


@router.get("")
def get_persistence(
    min_days: int = Query(2, ge=2),
    since: str = Query(None),
    limit: int = Query(100, ge=1, le=5000),
    db=Depends(get_db),
):
    params = {"min_days": min_days, "limit": limit}
    where = ""
    if since:
        where = "WHERE first_alert_time >= :since"
        params["since"] = f"{since} 00:00:00"

    query = f"""
        SELECT source_ip, target,
               COUNT(DISTINCT DATE(first_alert_time)) AS days,
               MIN(first_alert_time) AS first_seen,
               MAX(last_alert_time) AS last_seen,
               SUM(alert_count) AS total_alerts
        FROM alerts
        {where}
        GROUP BY source_ip, target
        HAVING days >= :min_days
        ORDER BY days DESC, total_alerts DESC
        LIMIT :limit
    """
    rows = db.execute(text(query), params).fetchall()
    items = []
    for r in rows:
        d = dict(r._mapping)
        for k in ("first_seen", "last_seen"):
            if k in d and d[k]:
                d[k] = str(d[k])
        items.append(d)
    return items
