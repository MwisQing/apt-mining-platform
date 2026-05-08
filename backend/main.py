import os
import mimetypes
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text
import gc

from backend.utils import get_config, reload_dicts
from backend.utils.db import get_engine, init_db
from backend.utils.logger import setup_logging
from backend.api import alerts, devices, events, tags, traced, imports, persistence, config as config_api

import logging

setup_logging()
logger = logging.getLogger("apt-mining")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    reload_dicts()
    # Periodic WAL checkpoint + memory cleanup to prevent degradation over time
    import asyncio
    checkpoint_count = 0
    async def checkpoint_wal():
        nonlocal checkpoint_count
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            try:
                from backend.utils.db import get_engine
                with get_engine().begin() as conn:
                    # PASSIVE every cycle for safety
                    conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
                    # TRUNCATE every 30 min (6 cycles) to actually shrink WAL
                    checkpoint_count += 1
                    if checkpoint_count % 6 == 0:
                        conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
                    # Limit WAL size
                    conn.execute(text("PRAGMA wal_autocheckpoint=1000"))
                # Force garbage collection to prevent memory bloat
                gc.collect()
            except Exception:
                logger.exception("WAL checkpoint failed")
    checkpoint_task = asyncio.create_task(checkpoint_wal())
    yield
    checkpoint_task.cancel()
    try:
        await checkpoint_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="APT Mining Workbench", version="1.0", lifespan=lifespan)

# CORS for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts.router)
app.include_router(alerts.candidate_router)
app.include_router(devices.router)
app.include_router(events.router)
app.include_router(tags.router)
app.include_router(traced.router)
app.include_router(imports.router)
app.include_router(persistence.router)
app.include_router(config_api.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Mount frontend static files in production (after API routes)
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
dist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

# SPA fallback: serve index.html for client-side routes (so /settings refresh works)
if os.path.exists(dist_path):
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # API routes are matched first, but if we get here, it's not an API path
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        # Try serving as a static file first
        file_path = os.path.join(dist_path, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Fallback to index.html for client-side routes (e.g. /settings, /events)
        index_path = os.path.join(dist_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Not Found")
