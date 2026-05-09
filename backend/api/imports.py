from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from datetime import datetime
import hashlib
import os
import re
import threading
import pandas as pd
import json
import csv
import io
import time
from sqlalchemy.exc import IntegrityError
from backend.utils.db import get_db, get_session_local, get_engine, write_audit
from backend.utils import get_path
from backend.services.alert_workbench import compute_alert_content_hash


router = APIRouter(prefix="/api/imports", tags=["imports"])

IMPORT_PROGRESS_BATCH_SIZE = 100  # update progress every N rows during sheet parsing
DB_LOCK_RETRY_ATTEMPTS = 12
DB_LOCK_RETRY_DELAY_SECONDS = 1
IMPORT_JOB_LOCK = threading.Lock()
ROW_STATUS_GROUPS = {
    "issues": ("raw_only", "failed"),
    "skipped": ("skipped_duplicate",),
    "raw_only": ("raw_only",),
}
CSV_EXPORT_TYPES = {
    "failures": ("raw_only", "failed"),
    "skipped": ("skipped_duplicate",),
    "raw_only": ("raw_only",),
}


FIELD_ALIASES = {
    "device_id": ["设备ID", "设备 ID", "终端ID", "主机ID", "device_id", "Device ID"],
    "first_alert_time": ["首次告警时间", "首次告警", "first_alert_time", "First Alert Time"],
    "last_alert_time": ["最近告警时间", "最后告警时间", "告警时间", "last_alert_time", "Last Alert Time"],
    "source_ip": ["源IP", "源 IP", "内网IP", "src_ip", "source_ip", "Source IP"],
    "target": ["外联目标", "目标", "访问目标", "目的IP", "域名", "target", "Target", "dst"],
    "port": ["外联端口", "端口", "目的端口", "dst_port", "port", "Port"],
    "threat_type": ["威胁类型", "threat_type", "Threat Type"],
    "threat_level": ["威胁等级", "threat_level", "Threat Level"],
    "std_apt_org": ["标准APT组织", "标准 APT 组织", "std_apt_org", "standard_apt_org"],
    "apt_org": ["APT组织", "APT 组织", "组织", "apt_org", "APT Org"],
    "apt_org_tier": ["APT组织分类", "APT 分级", "APT组织分级", "apt_org_tier"],
    "alert_count": ["告警次数", "次数", "alert_count", "Alert Count"],
    "vendors": ["厂商", "vendors", "Vendor"],
    "protocol": ["协议", "protocol", "Protocol"],
    "intel_tags": ["情报标签", "标签", "intel_tags", "Intel Tags"],
    "target_type": ["目标类型", "target_type", "Target Type"],
    "dns_resolved_ip": ["DNS解析IP", "DNS 解析 IP", "dns_resolved_ip"],
    "down_traffic": ["下行流量", "down_traffic"],
    "up_traffic": ["上行流量", "up_traffic"],
    "asset_type": ["资产类型", "asset_type"],
    "intel_position": ["情报位置", "intel_position"],
    "disposal_action": ["处置动作", "disposal_action"],
    "analysis_status": ["研判状态", "分析状态", "analysis_status"],
    "is_focused": ["重点关注", "是否关注", "is_focused"],
}


def _norm_column(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def _resolve_columns(columns):
    normalized = {_norm_column(column): column for column in columns}
    resolved = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            column = normalized.get(_norm_column(alias))
            if column is not None:
                resolved[field] = column
                break
    return resolved


def _json_safe(value):
    if pd.isna(value):
        return None
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip() if not isinstance(value, (int, float, bool)) else value


def _clean_cell(value):
    if pd.isna(value):
        return None
    text_value = str(value).strip()
    if not text_value or text_value.lower() == "nan":
        return None
    return text_value


def _get_cell(row, columns, field, default=None):
    column = columns.get(field)
    if not column:
        return default
    value = _clean_cell(row[column])
    return default if value is None else value


def _parse_datetime(value):
    text_value = _clean_cell(value)
    if not text_value:
        return None
    parsed = pd.to_datetime(
        text_value.replace("/", "-").replace(".", "-"),
        errors="coerce",
    )
    if pd.isna(parsed):
        return text_value
    return parsed.to_pydatetime().strftime("%Y-%m-%d %H:%M:%S")


def _parse_int(value, default=0):
    text_value = _clean_cell(value)
    if text_value is None:
        return default
    try:
        return int(float(text_value.replace(",", "")))
    except Exception:
        return default


def _row_payload(row):
    values = row.to_dict() if hasattr(row, "to_dict") else dict(row)
    return {str(key): _json_safe(value) for key, value in values.items()}


def _row_hash(source_file, sheet_name, excel_row_number, raw_json):
    raw = f"{source_file}|{sheet_name}|{excel_row_number}|{raw_json}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _update_import(db, import_id, **fields):
    if not fields:
        return
    params = {"id": import_id}
    updates = []
    for key, value in fields.items():
        updates.append(f"{key} = :{key}")
        params[key] = value
    db.execute(text(f"UPDATE imports SET {', '.join(updates)} WHERE id = :id"), params)


def _resolve_row_status_filters(status=None, status_group=None):
    if status:
        return (status,)
    if status_group:
        return ROW_STATUS_GROUPS.get(status_group, ())
    return ()


def _extract_export_value(raw_payload, normalized_payload, normalized_key, raw_keys):
    normalized_payload = normalized_payload or {}
    raw_payload = raw_payload or {}
    value = normalized_payload.get(normalized_key)
    if value not in (None, ""):
        return value
    for key in raw_keys:
        value = raw_payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _build_failure_export_rows(rows):
    exported = []
    for row in rows:
        raw_payload = row.get("raw")
        if raw_payload is None:
            raw_payload = json.loads(row.get("raw_json") or "{}")
        normalized_payload = row.get("normalized")
        if normalized_payload is None:
            normalized_payload = json.loads(row.get("normalized_json") or "{}") if row.get("normalized_json") else {}
        exported.append({
            "sheet": row.get("sheet_name"),
            "row": row.get("excel_row_number"),
            "status": row.get("parse_status"),
            "error": row.get("parse_error"),
            "device_id": _extract_export_value(raw_payload, normalized_payload, "device_id", ["设备ID", "设备 ID", "device_id"]),
            "target": _extract_export_value(raw_payload, normalized_payload, "target", ["外联目标", "目标", "target", "Target"]),
            "port": _extract_export_value(raw_payload, normalized_payload, "port", ["外联端口", "端口", "port", "Port"]),
        })
    return exported


def _should_run_vacuum(page_size, freelist_count, page_count):
    if not page_size or not freelist_count or not page_count:
        return False
    reclaim_bytes = page_size * freelist_count
    reclaim_ratio = freelist_count / max(page_count, 1)
    return reclaim_bytes >= 32 * 1024 * 1024 and reclaim_ratio >= 0.1


def _checkpoint_after_import_delete(raw_conn):
    raw_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _load_alert_id_map_for_hashes(db, content_hashes, batch_size=500):
    hash_to_alert_id = {}
    hashes = [item for item in content_hashes if item]
    for start in range(0, len(hashes), batch_size):
        batch = hashes[start:start + batch_size]
        if not batch:
            continue
        placeholders = ", ".join(f":hash_{idx}" for idx in range(len(batch)))
        rows = db.execute(text(
            "SELECT id, content_hash FROM alerts WHERE content_hash IN "
            f"({placeholders})"
        ), {f"hash_{idx}": value for idx, value in enumerate(batch)}).fetchall()
        for row in rows:
            hash_to_alert_id[row[1]] = row[0]
    return hash_to_alert_id


def _rebuild_import_row_updates_for_repair(rows, parsed_alert_map=None, existing_hashes=None):
    parsed_alert_map = parsed_alert_map or {}
    workbook_seen_hashes = set(existing_hashes or set())
    updates = []
    stats = {"parsed": 0, "raw_only": 0, "failed": 0}

    for row in rows:
        raw_payload = json.loads(row.get("raw_json") or "{}")
        try:
            item, parse_error = _alert_from_row(raw_payload, _resolve_columns(list(raw_payload.keys())))
            if parse_error:
                stats["raw_only"] += 1
                updates.append({
                    "id": row["id"],
                    "parse_status": "raw_only",
                    "parse_error": parse_error,
                    "normalized_json": None,
                    "alert_id": None,
                })
                continue

            content_hash = item["content_hash"]
            alert_info = parsed_alert_map.get(row["id"])
            if alert_info:
                stats["parsed"] += 1
                workbook_seen_hashes.add(content_hash)
                updates.append({
                    "id": row["id"],
                    "parse_status": "parsed",
                    "parse_error": None,
                    "normalized_json": json.dumps(item, ensure_ascii=False, default=str),
                    "alert_id": alert_info.get("alert_id"),
                })
                continue

            if content_hash in workbook_seen_hashes:
                stats["parsed"] += 1
                updates.append({
                    "id": row["id"],
                    "parse_status": "skipped_duplicate",
                    "parse_error": None,
                    "normalized_json": json.dumps(item, ensure_ascii=False, default=str),
                    "alert_id": None,
                })
                continue

            workbook_seen_hashes.add(content_hash)
            stats["parsed"] += 1
            updates.append({
                "id": row["id"],
                "parse_status": "parsed",
                "parse_error": None,
                "normalized_json": json.dumps(item, ensure_ascii=False, default=str),
                "alert_id": None,
            })
        except Exception as exc:
            stats["failed"] += 1
            updates.append({
                "id": row["id"],
                "parse_status": "failed",
                "parse_error": str(exc),
                "normalized_json": None,
                "alert_id": None,
            })

    return updates, stats


def _is_db_locked_error(exc):
    return "database is locked" in str(exc).lower()


def _run_locked_retry(db, operation, *, retries=DB_LOCK_RETRY_ATTEMPTS):
    last_error = None
    for attempt in range(retries):
        try:
            return operation()
        except Exception as exc:
            if not _is_db_locked_error(exc) or attempt == retries - 1:
                raise
            last_error = exc
            db.rollback()
            time.sleep(DB_LOCK_RETRY_DELAY_SECONDS)
    raise last_error


def _alert_from_row(row, columns):
    device_id = _get_cell(row, columns, "device_id")
    source_ip = _get_cell(row, columns, "source_ip")
    target = _get_cell(row, columns, "target")
    first_alert_time = _parse_datetime(_get_cell(row, columns, "first_alert_time"))
    last_alert_time = _parse_datetime(_get_cell(row, columns, "last_alert_time"))
    if not first_alert_time:
        first_alert_time = last_alert_time
    if not last_alert_time:
        last_alert_time = first_alert_time

    missing = []
    if not device_id and not source_ip:
        missing.append("设备ID或源IP")
    if not target:
        missing.append("外联目标")
    if not last_alert_time:
        missing.append("告警时间")
    if missing:
        return None, "缺少核心字段: " + "、".join(missing)

    if not device_id:
        device_id = source_ip
    if not source_ip:
        source_ip = device_id

    port = _get_cell(row, columns, "port")
    std_apt_org = _get_cell(row, columns, "std_apt_org")
    item = {
        "device_id": device_id,
        "first_alert_time": first_alert_time,
        "last_alert_time": last_alert_time,
        "source_ip": source_ip,
        "target": target,
        "target_type": _get_cell(row, columns, "target_type"),
        "port": port,
        "threat_type": _get_cell(row, columns, "threat_type"),
        "threat_level": _get_cell(row, columns, "threat_level"),
        "std_apt_org": std_apt_org.lower() if std_apt_org else None,
        "apt_org": _get_cell(row, columns, "apt_org"),
        "apt_org_tier": _get_cell(row, columns, "apt_org_tier"),
        "alert_count": _parse_int(_get_cell(row, columns, "alert_count")),
        "vendors": _get_cell(row, columns, "vendors"),
        "protocol": _get_cell(row, columns, "protocol"),
        "intel_tags": _get_cell(row, columns, "intel_tags"),
        "intel_position": _get_cell(row, columns, "intel_position"),
        "disposal_action": _get_cell(row, columns, "disposal_action"),
        "dns_resolved_ip": _get_cell(row, columns, "dns_resolved_ip"),
        "down_traffic": _parse_int(_get_cell(row, columns, "down_traffic")),
        "up_traffic": _parse_int(_get_cell(row, columns, "up_traffic")),
        "asset_type": _get_cell(row, columns, "asset_type"),
    }
    item["content_hash"] = compute_alert_content_hash(item)
    item["unique_hash"] = item["content_hash"]
    return item, None


def _insert_alert(db, item):
    row = db.execute(text(
        "SELECT id FROM alerts WHERE content_hash = :content_hash LIMIT 1"
    ), {"content_hash": item["content_hash"]}).fetchone()
    if row:
        return False, row[0]

    try:
        result = db.execute(text(
        "INSERT INTO alerts ("
        "device_id, first_alert_time, last_alert_time, source_ip, target, "
        "target_type, port, threat_type, threat_level, std_apt_org, "
        "apt_org, apt_org_tier, alert_count, vendors, protocol, "
        "intel_tags, intel_position, disposal_action, dns_resolved_ip, down_traffic, up_traffic, asset_type, "
        "source_file, imported_at, unique_hash, content_hash, import_id, import_sheet_id, "
        "import_row_id, sheet_name, excel_row_number, raw_row_hash"
        ") VALUES ("
        ":device_id, :first_alert_time, :last_alert_time, :source_ip, :target, "
        ":target_type, :port, :threat_type, :threat_level, :std_apt_org, "
        ":apt_org, :apt_org_tier, :alert_count, :vendors, :protocol, "
        ":intel_tags, :intel_position, :disposal_action, :dns_resolved_ip, :down_traffic, :up_traffic, :asset_type, "
        ":source_file, :imported_at, :unique_hash, :content_hash, :import_id, :import_sheet_id, "
        ":import_row_id, :sheet_name, :excel_row_number, :raw_row_hash"
        ")"
    ), item)
        return True, result.lastrowid
    except IntegrityError:
        row = db.execute(text(
            "SELECT id FROM alerts WHERE content_hash = :content_hash OR unique_hash = :unique_hash LIMIT 1"
        ), {
            "content_hash": item["content_hash"],
            "unique_hash": item["unique_hash"],
        }).fetchone()
        return False, row[0] if row else None


def _process_excel(file_path: str, source_file: str, import_id: int, db) -> dict:
    workbook = pd.ExcelFile(file_path)
    imported_at = datetime.now().isoformat()
    totals = {
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
        "raw_only": 0,
        "total_rows": 0,
        "parsed_rows": 0,
        "failures": [],
    }

    # Speed up SQLite for bulk import
    db.execute(text("PRAGMA synchronous=NORMAL"))
    db.execute(text("PRAGMA cache_size=-8000"))
    db.execute(text("PRAGMA temp_store=MEMORY"))
    db.execute(text("PRAGMA mmap_size=30000000000"))

    # Pre-fetch existing content hashes for dedup (use set for O(1) lookup)
    existing_hashes = set()
    hash_rows = db.execute(text("SELECT content_hash FROM alerts WHERE content_hash IS NOT NULL AND content_hash != ''")).fetchall()
    for r in hash_rows:
        existing_hashes.add(r[0])
    # Track hashes across the whole workbook, not just a single sheet. Otherwise
    # duplicates across different sheets can slip into a later bulk INSERT and
    # cause the whole batch to fail, which looks like "first import incomplete,
    # second import fills the gap".
    workbook_seen_hashes = set(existing_hashes)
    # Free the cursor results to help GC
    hash_rows = None

    for sheet_index, sheet_name in enumerate(workbook.sheet_names):
        sheet_started_at = datetime.now().isoformat()
        sheet_id = db.execute(text(
            "INSERT INTO import_sheets ("
            "import_id, sheet_name, sheet_index, header_row, headers_json, row_count, "
            "parsed_rows, raw_rows, failed_rows, status, created_at"
            ") VALUES (:import_id, :sheet_name, :sheet_index, 1, '[]', 0, 0, 0, 0, 'processing', :created_at)"
        ), {
            "import_id": import_id,
            "sheet_name": sheet_name,
            "sheet_index": sheet_index,
            "created_at": sheet_started_at,
        }).lastrowid

        sheet_counts = {"row_count": 0, "parsed": 0, "raw": 0, "failed": 0}
        try:
            df = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
            headers = [str(column) for column in df.columns]
            columns = _resolve_columns(headers)
            totals["total_rows"] += len(df)

            db.execute(text(
                "UPDATE import_sheets SET headers_json = :headers_json, row_count = :row_count WHERE id = :id"
            ), {
                "headers_json": json.dumps(headers, ensure_ascii=False),
                "row_count": len(df),
                "id": sheet_id,
            })

            # Phase 1: Batch insert all import_rows first
            import_row_params = []
            raw_records = list(df.to_dict("records"))
            for idx, row in enumerate(raw_records):
                excel_row_number = int(idx) + 2
                raw_payload = _row_payload(row)
                raw_json = json.dumps(raw_payload, ensure_ascii=False, default=str)
                raw_hash = _row_hash(source_file, sheet_name, excel_row_number, raw_json)
                import_row_params.append({
                    "import_id": import_id,
                    "sheet_id": sheet_id,
                    "source_file": source_file,
                    "sheet_name": sheet_name,
                    "excel_row_number": excel_row_number,
                    "raw_json": raw_json,
                    "row_hash": raw_hash,
                    "created_at": imported_at,
                })

            # Insert import_rows in batches of 500
            BATCH = 500
            for batch_start in range(0, len(import_row_params), BATCH):
                batch = import_row_params[batch_start:batch_start + BATCH]
                placeholders = []
                values = {}
                for bi, p in enumerate(batch):
                    i = batch_start + bi
                    placeholders.append(
                        f"(:imp_{i}, :sh_{i}, :sf_{i}, :sn_{i}, "
                        f":ern_{i}, :rj_{i}, 'uploaded', NULL, :rh_{i}, NULL, :ca_{i})"
                    )
                    values.update({
                        f"imp_{i}": p["import_id"],
                        f"sh_{i}": p["sheet_id"],
                        f"sf_{i}": p["source_file"],
                        f"sn_{i}": p["sheet_name"],
                        f"ern_{i}": p["excel_row_number"],
                        f"rj_{i}": p["raw_json"],
                        f"rh_{i}": p["row_hash"],
                        f"ca_{i}": p["created_at"],
                    })
                db.execute(text(
                    f"INSERT INTO import_rows ("
                    f"import_id, import_sheet_id, source_file, sheet_name, excel_row_number, "
                    f"raw_json, parse_status, parse_error, row_hash, alert_id, created_at"
                    f") VALUES {', '.join(placeholders)}"
                ), values)

            # Get the inserted row IDs
            first_row_id = db.execute(text(
                "SELECT MIN(id) FROM import_rows WHERE import_id = :import_id AND import_sheet_id = :sheet_id"
            ), {"import_id": import_id, "sheet_id": sheet_id}).scalar()

            # Phase 2: Parse and insert alerts in memory, then batch DB ops
            alert_inserts = []
            import_row_updates = []
            sheet_parsed_count = 0  # rows processed so far in this sheet

            for idx, row in enumerate(raw_records):
                excel_row_number = int(idx) + 2
                import_row_id = first_row_id + idx
                sheet_counts["row_count"] += 1

                try:
                    item, parse_error = _alert_from_row(row, columns)
                    if parse_error:
                        sheet_counts["raw"] += 1
                        totals["raw_only"] += 1
                        import_row_updates.append({
                            "id": import_row_id,
                            "parse_status": "raw_only",
                            "parse_error": parse_error,
                            "normalized_json": None,
                            "alert_id": None,
                        })
                        continue

                    content_hash = item["content_hash"]
                    if content_hash in workbook_seen_hashes:
                        totals["skipped"] += 1
                        sheet_counts["parsed"] += 1
                        totals["parsed_rows"] += 1
                        import_row_updates.append({
                            "id": import_row_id,
                            "parse_status": "skipped_duplicate",
                            "parse_error": None,
                            "normalized_json": json.dumps(item, ensure_ascii=False, default=str),
                            "alert_id": None,
                        })
                        continue

                    workbook_seen_hashes.add(content_hash)
                    totals["inserted"] += 1
                    totals["parsed_rows"] += 1
                    sheet_counts["parsed"] += 1

                    item.update({
                        "source_file": source_file,
                        "imported_at": imported_at,
                        "import_id": import_id,
                        "import_sheet_id": sheet_id,
                        "import_row_id": import_row_id,
                        "sheet_name": sheet_name,
                        "excel_row_number": excel_row_number,
                        "raw_row_hash": import_row_params[idx]["row_hash"],
                    })
                    alert_inserts.append(item)
                    import_row_updates.append({
                        "id": import_row_id,
                        "parse_status": "parsed",
                        "parse_error": None,
                        "normalized_json": json.dumps(item, ensure_ascii=False, default=str),
                        "alert_id": None,  # Will be filled after INSERT
                        "content_hash": content_hash,
                    })

                except Exception as e:
                    sheet_counts["failed"] += 1
                    totals["failed"] += 1
                    totals["failures"].append({
                        "sheet": sheet_name,
                        "row": excel_row_number,
                        "error": str(e),
                    })
                    import_row_updates.append({
                        "id": import_row_id,
                        "parse_status": "failed",
                        "parse_error": str(e),
                        "normalized_json": None,
                        "alert_id": None,
                        "content_hash": None,
                    })
                finally:
                    sheet_parsed_count += 1
                    if sheet_parsed_count % IMPORT_PROGRESS_BATCH_SIZE == 0:
                        _update_import(
                            db,
                            import_id,
                            raw_rows=sheet_parsed_count,
                            total_rows=totals["total_rows"],
                            status="processing",
                        )
                        db.commit()

            # Phase 3: Batch insert alerts
            if alert_inserts:
                for batch_start in range(0, len(alert_inserts), BATCH):
                    batch = alert_inserts[batch_start:batch_start + BATCH]
                    placeholders = []
                    values = {}
                    cols = [
                        "device_id", "first_alert_time", "last_alert_time", "source_ip", "target",
                        "target_type", "port", "threat_type", "threat_level", "std_apt_org",
                        "apt_org", "apt_org_tier", "alert_count", "vendors", "protocol",
                        "intel_tags", "dns_resolved_ip", "down_traffic", "up_traffic", "asset_type",
                        "source_file", "imported_at", "unique_hash", "content_hash", "import_id",
                        "import_sheet_id", "import_row_id", "sheet_name", "excel_row_number", "raw_row_hash",
                    ]
                    for bi, item in enumerate(batch):
                        i = batch_start + bi
                        named = [f":{col}_{i}" for col in cols]
                        placeholders.append(f"({', '.join(named)})")
                        for col in cols:
                            values[f"{col}_{i}"] = item.get(col)
                    db.execute(text(
                        f"INSERT INTO alerts ({', '.join(cols)}) VALUES {', '.join(placeholders)}"
                    ), values)

                # Fetch back the inserted alert IDs in small batches to avoid
                # SQLite "too many SQL variables" on large imports.
                hash_to_alert_id = _load_alert_id_map_for_hashes(
                    db,
                    [item["content_hash"] for item in alert_inserts],
                )

                # Update import_row_updates with correct alert_ids
                for upd in import_row_updates:
                    if upd.get("parse_status") == "parsed":
                        upd["alert_id"] = hash_to_alert_id.get(upd.get("content_hash"))

            # Phase 4: Batch update import_rows
            for batch_start in range(0, len(import_row_updates), BATCH):
                batch = import_row_updates[batch_start:batch_start + BATCH]
                for upd in batch:
                    upd = dict(upd)
                    upd.pop("content_hash", None)
                    db.execute(text(
                        "UPDATE import_rows SET parse_status = :parse_status, parse_error = :parse_error, "
                        "normalized_json = :normalized_json, alert_id = :alert_id WHERE id = :id"
                    ), upd)

            # Final sheet update
            db.execute(text(
                "UPDATE import_sheets SET row_count = :row_count, parsed_rows = :parsed, "
                "raw_rows = :raw, failed_rows = :failed, status = :status WHERE id = :id"
            ), {
                "row_count": sheet_counts["row_count"],
                "parsed": sheet_counts["parsed"],
                "raw": sheet_counts["raw"],
                "failed": sheet_counts["failed"],
                "status": "success" if sheet_counts["failed"] == 0 and sheet_counts["raw"] == 0 else "partial",
                "id": sheet_id,
            })
            _update_import(
                db,
                import_id,
                rows_inserted=totals["inserted"],
                rows_skipped=totals["skipped"],
                rows_failed=totals["failed"],
                total_rows=totals["total_rows"],
                parsed_rows=totals["parsed_rows"],
                raw_rows=totals["raw_only"],
                status="processing",
            )
            # Single commit per sheet
            db.commit()

        except Exception as e:
            totals["failed"] += 1
            error = str(e)
            totals["failures"].append({"sheet": sheet_name, "row": None, "error": error})
            try:
                db.execute(text(
                    "UPDATE import_sheets SET failed_rows = 1, status = 'failed' WHERE id = :id"
                ), {"id": sheet_id})
                db.commit()
            except Exception:
                db.rollback()

    # Restore SQLite settings
    db.execute(text("PRAGMA synchronous=FULL"))
    db.commit()
    return totals


def _run_import_job(import_id: int, file_path: str, source_file: str):
    with IMPORT_JOB_LOCK:
        db = get_session_local()()
        try:
            _update_import(db, import_id, status="processing")
            db.commit()

            result = _process_excel(file_path, source_file, import_id, db)
            status = "success"
            if result["failed"] > 0 or result["raw_only"] > 0:
                status = "partial" if (result["inserted"] or result["skipped"] or result["raw_only"]) else "failed"

            _update_import(
                db,
                import_id,
                rows_inserted=result["inserted"],
                rows_skipped=result["skipped"],
                rows_failed=result["failed"],
                total_rows=result["total_rows"],
                parsed_rows=result["parsed_rows"],
                raw_rows=result["raw_only"],
                status=status,
                log=json.dumps(result["failures"], ensure_ascii=False),
            )
            write_audit(db, "import_excel", "import", import_id, {
                "source_file": source_file,
                "inserted": result["inserted"],
                "skipped": result["skipped"],
                "raw_only": result["raw_only"],
                "failed": result["failed"],
                "total_rows": result["total_rows"],
            })
            db.commit()
        except Exception as e:
            _update_import(
                db,
                import_id,
                rows_inserted=0,
                rows_skipped=0,
                rows_failed=1,
                total_rows=0,
                parsed_rows=0,
                raw_rows=0,
                status="failed",
                log=json.dumps([{"row": None, "error": str(e)}], ensure_ascii=False),
            )
            write_audit(db, "import_excel_failed", "import", import_id, {
                "source_file": source_file,
                "error": str(e),
            })
            db.commit()
        finally:
            db.close()


def _repair_import_rows_if_needed(db, import_id):
    pending = db.execute(text(
        "SELECT COUNT(*) FROM import_rows WHERE import_id = :id AND parse_status = 'uploaded'"
    ), {"id": import_id}).scalar() or 0
    if pending == 0:
        return

    rows = db.execute(text(
        "SELECT id, raw_json, import_sheet_id, excel_row_number "
        "FROM import_rows WHERE import_id = :id "
        "ORDER BY import_sheet_id, excel_row_number"
    ), {"id": import_id}).fetchall()
    parsed_rows = db.execute(text(
        "SELECT import_row_id, id AS alert_id FROM alerts "
        "WHERE import_id = :id AND import_row_id IS NOT NULL"
    ), {"id": import_id}).fetchall()
    parsed_alert_map = {row[0]: {"alert_id": row[1]} for row in parsed_rows}

    updates, _stats = _rebuild_import_row_updates_for_repair(
        [dict(row._mapping) for row in rows],
        parsed_alert_map=parsed_alert_map,
        existing_hashes=set(),
    )
    for upd in updates:
        db.execute(text(
            "UPDATE import_rows SET parse_status = :parse_status, parse_error = :parse_error, "
            "normalized_json = :normalized_json, alert_id = COALESCE(:alert_id, alert_id) WHERE id = :id"
        ), upd)
    db.commit()


async def _save_upload_file(file: UploadFile, file_path: str):
    with open(file_path, "wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    await file.close()


def _start_import_thread(import_id: int, file_path: str, source_file: str):
    thread = threading.Thread(
        target=_run_import_job,
        args=(import_id, file_path, source_file),
        daemon=True,
        name=f"import-{import_id}",
    )
    thread.start()


@router.post("")
async def import_excel(files: list[UploadFile] = File(...), db=Depends(get_db)):
    upload_dir = get_path("upload_tmp")
    os.makedirs(upload_dir, exist_ok=True)
    jobs = []
    session_local = get_session_local()

    for file in files:
        filename = os.path.basename(file.filename)
        now = datetime.now().isoformat()
        holder = {}
        record_db = session_local()

        def _create_import_record():
            cursor = record_db.execute(text(
                "INSERT INTO imports ("
                "source_file, imported_at, rows_inserted, rows_skipped, rows_failed, "
                "total_rows, parsed_rows, raw_rows, status, log"
                ") VALUES (:source_file, :imported_at, 0, 0, 0, 0, 0, 0, 'uploaded', '[]')"
            ), {"source_file": filename, "imported_at": now})
            holder["import_id"] = cursor.lastrowid
            write_audit(record_db, "upload_import_file", "import", holder["import_id"], {"source_file": filename})
            record_db.commit()

        try:
            _run_locked_retry(record_db, _create_import_record)
        finally:
            record_db.close()
        import_id = holder["import_id"]
        stored_name = f"import_{import_id}_{filename}"
        file_path = os.path.join(upload_dir, stored_name)
        await _save_upload_file(file, file_path)

        _start_import_thread(import_id, file_path, filename)
        jobs.append({"id": import_id, "source_file": filename, "status": "uploaded"})

    return {"accepted": len(jobs), "jobs": jobs}


def _import_item(row):
    d = dict(row._mapping)
    if d.get("imported_at"):
        d["imported_at"] = str(d["imported_at"])
    for field in ("rows_inserted", "rows_skipped", "rows_failed", "total_rows", "parsed_rows", "raw_rows"):
        d[field] = d.get(field) or 0
    d["scope"] = {
        "imports_all_sheets": True,
        "imports_original_rows": True,
        "dedupe_policy": "exact_alert_content_with_time",
        "traceability": "alert.import_row_id -> import_rows.id",
    }
    return d


@router.get("")
def list_imports(db=Depends(get_db)):
    rows = db.execute(text("SELECT * FROM imports ORDER BY imported_at DESC")).fetchall()
    return [_import_item(row) for row in rows]


@router.get("/{import_id}")
def get_import(import_id: int, db=Depends(get_db)):
    row = db.execute(text("SELECT * FROM imports WHERE id = :id"), {"id": import_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Import not found")
    return _import_item(row)


@router.get("/{import_id}/sheets")
def list_import_sheets(import_id: int, db=Depends(get_db)):
    rows = db.execute(text(
        "SELECT * FROM import_sheets WHERE import_id = :import_id ORDER BY sheet_index"
    ), {"import_id": import_id}).fetchall()
    items = []
    for row in rows:
        item = dict(row._mapping)
        item["headers"] = json.loads(item.get("headers_json") or "[]")
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])
        items.append(item)
    return items


@router.get("/{import_id}/rows")
def list_import_rows(
    import_id: int,
    sheet_id: int = Query(None),
    status: str = Query(None),
    status_group: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    db=Depends(get_db),
):
    _repair_import_rows_if_needed(db, import_id)
    where = ["import_id = :import_id"]
    params = {"import_id": import_id}
    if sheet_id:
        where.append("import_sheet_id = :sheet_id")
        params["sheet_id"] = sheet_id
    statuses = _resolve_row_status_filters(status=status, status_group=status_group)
    if status_group and not statuses:
        raise HTTPException(status_code=400, detail="Invalid status_group")
    if statuses:
        if len(statuses) == 1:
            where.append("parse_status = :status")
            params["status"] = statuses[0]
        else:
            placeholders = []
            for idx, item in enumerate(statuses):
                key = f"status_{idx}"
                placeholders.append(f":{key}")
                params[key] = item
            where.append(f"parse_status IN ({', '.join(placeholders)})")
    where_sql = " AND ".join(where)
    total = db.execute(text(f"SELECT COUNT(*) FROM import_rows WHERE {where_sql}"), params).scalar() or 0
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = db.execute(text(f"""
        SELECT * FROM import_rows
        WHERE {where_sql}
        ORDER BY import_sheet_id, excel_row_number
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    items = []
    for row in rows:
        item = dict(row._mapping)
        item["raw"] = json.loads(item.get("raw_json") or "{}")
        item["normalized"] = json.loads(item.get("normalized_json") or "{}") if item.get("normalized_json") else None
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])
        items.append(item)

    if total == 0 and status_group == "issues":
        import_row = db.execute(text(
            "SELECT log FROM imports WHERE id = :id"
        ), {"id": import_id}).fetchone()
        failures = json.loads(import_row[0] or "[]") if import_row else []
        synthetic_items = []
        for idx, failure in enumerate(failures):
            synthetic_items.append({
                "id": f"log-{idx}",
                "import_id": import_id,
                "import_sheet_id": None,
                "source_file": None,
                "sheet_name": failure.get("sheet"),
                "excel_row_number": failure.get("row"),
                "raw": {},
                "normalized": None,
                "parse_status": "failed",
                "parse_error": failure.get("error"),
                "alert_id": None,
                "created_at": None,
            })
        if synthetic_items:
            total = len(synthetic_items)
            start = (page - 1) * page_size
            end = start + page_size
            items = synthetic_items[start:end]

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{import_id}/failures.csv")
def download_failures(
    import_id: int,
    type: str = Query("failures"),
    db=Depends(get_db),
):
    statuses = CSV_EXPORT_TYPES.get(type)
    if not statuses:
        raise HTTPException(status_code=400, detail="Invalid export type")
    status_placeholders = ", ".join(f":status_{idx}" for idx in range(len(statuses)))
    params = {"id": import_id, **{f"status_{idx}": item for idx, item in enumerate(statuses)}}
    rows = db.execute(text(
        "SELECT sheet_name, excel_row_number, parse_status, parse_error, raw_json, normalized_json "
        "FROM import_rows "
        f"WHERE import_id = :id AND parse_status IN ({status_placeholders}) "
        "ORDER BY import_sheet_id, excel_row_number"
    ), params).fetchall()
    if not rows:
        row = db.execute(text(
            "SELECT source_file, log FROM imports WHERE id = :id"
        ), {"id": import_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Import not found")
        if type != "failures":
            failures = []
        else:
            failures = json.loads(row[1] or "[]")
    else:
        failures = _build_failure_export_rows([
            {
                "sheet_name": row[0],
                "excel_row_number": row[1],
                "parse_status": row[2],
                "parse_error": row[3],
                "raw_json": row[4],
                "normalized_json": row[5],
            }
            for row in rows
        ])
    if not failures:
        raise HTTPException(status_code=404, detail="No failures for this import")

    buf = io.StringIO()
    fieldnames = sorted({key for item in failures for key in item.keys()}) or ["error"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for item in failures:
        writer.writerow(item)
    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    filename = f"import_{import_id}_{type}.csv"
    return StreamingResponse(
        data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.delete("/{import_id}")
def delete_import(import_id: int, db=Depends(get_db)):
    row = db.execute(text("SELECT source_file FROM imports WHERE id = :id"), {"id": import_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Import not found")
    source_file = row[0]
    db.execute(text("DELETE FROM alerts WHERE import_id = :import_id"), {"import_id": import_id})
    db.execute(text(
        "DELETE FROM alerts WHERE source_file = :source_file AND import_id IS NULL"
    ), {"source_file": source_file})
    db.execute(text("DELETE FROM import_rows WHERE import_id = :id"), {"id": import_id})
    db.execute(text("DELETE FROM import_sheets WHERE import_id = :id"), {"id": import_id})
    db.execute(text("DELETE FROM imports WHERE id = :id"), {"id": import_id})
    write_audit(db, "delete_import", "import", import_id, {"source_file": source_file})
    db.commit()

    # Delete the uploaded Excel file from uploads/
    upload_dir = get_path("upload_tmp")
    stored_name = f"import_{import_id}_{source_file}"
    file_path = os.path.join(upload_dir, stored_name)
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass

    # Close the ORM session before VACUUM to release any implicit locks
    db.close()

    # Keep post-delete cleanup lightweight. We only checkpoint WAL here and
    # avoid proactively compacting the main DB file on every import delete.
    engine = get_engine()
    raw_conn = engine.raw_connection()
    try:
        _checkpoint_after_import_delete(raw_conn)
    except Exception:
        pass
    finally:
        if raw_conn is not None:
            raw_conn.close()

    return {"ok": True}
