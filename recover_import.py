#!/usr/bin/env python3
"""Re-import an uploaded Excel file that was not processed due to server restart/timeout."""
import sys
import os
import time
from pathlib import Path

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from backend.utils.db import get_session_local, init_db, write_audit
from backend.api.imports import _process_excel
from backend.services.snapshot_builder import rebuild_candidate_snapshots
from datetime import datetime


def recover_import(file_path: str):
    init_db()
    db = get_session_local()()

    filename = os.path.basename(file_path)
    now = datetime.now().isoformat()

    # Create import record
    cursor = db.execute(text(
        "INSERT INTO imports ("
        "source_file, imported_at, rows_inserted, rows_skipped, rows_failed, "
        "total_rows, parsed_rows, raw_rows, status, log"
        ") VALUES (:source_file, :imported_at, 0, 0, 0, 0, 0, 0, 'processing', '[]')"
    ), {"source_file": filename, "imported_at": now})
    import_id = cursor.lastrowid
    db.commit()
    print(f"[1/3] Import record created: id={import_id}, file={filename}")

    try:
        result = _process_excel(file_path, filename, import_id, db)
        db.commit()
        print(
            f"[2/3] Processing done: "
            f"inserted={result['inserted']}, skipped={result['skipped']}, "
            f"raw_only={result['raw_only']}, failed={result['failed']}, total={result['total_rows']}"
        )

        write_audit(db, "import_excel", "import", import_id, {
            "source_file": filename,
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "raw_only": result["raw_only"],
            "failed": result["failed"],
            "total_rows": result["total_rows"],
            "mode": "recover",
        })
        db.commit()

        print("[3/3] Rebuilding candidate snapshot...")
        rebuild_candidate_snapshots(db)
        print("Snapshot rebuilt. Recovery complete!")

    except Exception as e:
        db.execute(text(
            "UPDATE imports SET status = 'failed', log = :log WHERE id = :id"
        ), {"log": f"recovery failed: {e}", "id": import_id})
        db.commit()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    files = [f for f in os.listdir(uploads_dir) if f.endswith((".xlsx", ".xls"))]

    if not files:
        print("No files found in uploads/")
        sys.exit(1)

    # Use the most recent file (by modification time)
    target = max(files, key=lambda f: os.path.getmtime(os.path.join(uploads_dir, f)))
    file_path = os.path.join(uploads_dir, target)
    print(f"Target file: {target} ({os.path.getsize(file_path) / 1024 / 1024:.1f} MB)")

    start = time.time()
    recover_import(file_path)
    print(f"\nTotal time: {time.time() - start:.1f}s")
