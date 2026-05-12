from fastapi import APIRouter, Depends

from backend.services.snapshot_builder import (
    SNAPSHOT_TYPE_ALERT_CANDIDATES,
    get_snapshot_meta,
    rebuild_candidate_snapshots_async,
)
from backend.utils.db import get_db


router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("/status")
def get_snapshot_status(db=Depends(get_db)):
    return get_snapshot_meta(db, snapshot_type=SNAPSHOT_TYPE_ALERT_CANDIDATES)


@router.post("/rebuild")
def rebuild_snapshots(db=Depends(get_db)):
    rebuild_candidate_snapshots_async()
    return {"ok": True, "started": True}
