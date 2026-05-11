import argparse
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.utils as utils
import backend.utils.db as db_utils
from backend.api.alerts import query_alert_candidates, query_alerts
from backend.api.tags import get_batch, remove_devices_from_batch, restore_batch
from backend.api.imports import _insert_alert
from backend.services.alert_workbench import compute_alert_content_hash
from backend.utils.db import get_session_local


def _point_runtime_db(db_path):
    cfg = utils.load_config()
    cfg["paths"]["db"] = str(db_path)
    utils._config = cfg
    db_utils._engine = None
    db_utils._SessionLocal = None
    db_utils.init_db()


def _insert_alert_fixture(session, **overrides):
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    item = {
        "device_id": "DEV-001",
        "first_alert_time": "2026-04-29 09:00:00",
        "last_alert_time": "2026-04-29 09:05:00",
        "source_ip": "10.0.0.1",
        "target": "evil.example.com",
        "target_type": "domain",
        "port": "443",
        "threat_type": "APT,远控",
        "threat_level": "高",
        "std_apt_org": "apt28",
        "apt_org": "Fancy Bear",
        "apt_org_tier": "A",
        "alert_count": 4,
        "vendors": "VendorA,VendorB",
        "protocol": "https",
        "intel_tags": "apt,c2",
        "dns_resolved_ip": "198.51.100.7",
        "down_traffic": 1024,
        "up_traffic": 256,
        "asset_type": "server",
        "source_file": "smoke_fixture.xlsx",
        "imported_at": now,
        "import_id": None,
        "import_sheet_id": None,
        "import_row_id": None,
        "sheet_name": "Sheet1",
        "excel_row_number": 2,
        "raw_row_hash": None,
    }
    item.update(overrides)
    item["content_hash"] = compute_alert_content_hash(item)
    item["unique_hash"] = item["content_hash"]
    inserted, alert_id = _insert_alert(session, item)
    if not inserted:
        raise RuntimeError(f"Fixture alert was not inserted: {item['device_id']} -> {item['target']}")
    return alert_id


def _seed_minimal_dataset(session):
    if session.execute(db_utils.text("SELECT COUNT(*) FROM alerts")).scalar():
        return False

    _insert_alert_fixture(session)
    _insert_alert_fixture(
        session,
        device_id="DEV-002",
        source_ip="10.0.0.2",
        first_alert_time="2026-04-29 09:10:00",
        last_alert_time="2026-04-29 09:20:00",
        threat_type="远控",
        threat_level="中",
        std_apt_org=None,
        apt_org=None,
        apt_org_tier=None,
        alert_count=2,
        vendors="VendorA",
        intel_tags="remote",
    )
    _insert_alert_fixture(
        session,
        device_id="DEV-003",
        source_ip="10.0.0.3",
        target="198.51.100.7",
        target_type="ip",
        port="8080",
        first_alert_time="2026-04-29 10:00:00",
        last_alert_time="2026-04-29 10:05:00",
        threat_type="APT",
        threat_level="高",
        std_apt_org="apt41",
        apt_org="APT41",
        apt_org_tier="S",
        alert_count=1,
        vendors="VendorA,VendorC",
        intel_tags="apt,loader",
    )
    _insert_alert_fixture(
        session,
        device_id="DEV-004",
        source_ip="10.0.0.4",
        target="scan.example.net",
        target_type="domain",
        port="80",
        first_alert_time="2026-04-29 11:00:00",
        last_alert_time="2026-04-29 11:01:00",
        threat_type="扫描",
        threat_level="低",
        std_apt_org=None,
        apt_org=None,
        apt_org_tier=None,
        alert_count=1,
        vendors="VendorD",
        intel_tags="scan",
    )

    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
    session.execute(
        db_utils.text(
            "INSERT INTO traced_targets (target, port, traced_at, note) "
            "VALUES (:target, :port, :traced_at, :note)"
        ),
        {"target": "evil.example.com", "port": "443", "traced_at": now, "note": "fixture trace"},
    )
    batch_id = session.execute(
        db_utils.text(
            "INSERT INTO tag_batches (batch_name, created_at, note, status, device_ids_snapshot) "
            "VALUES (:name, :created_at, :note, 'active', :device_ids_snapshot)"
        ),
        {
            "name": "fixture batch",
            "created_at": now,
            "note": "fixture",
            "device_ids_snapshot": '["DEV-001"]',
        },
    ).lastrowid
    tag_id = session.execute(
        db_utils.text(
            "INSERT INTO tags (name, color, is_permanent, batch_id, created_at, note) "
            "VALUES (:name, :color, 0, :batch_id, :created_at, :note)"
        ),
        {
            "name": "重点设备",
            "color": "#fa8c16",
            "batch_id": batch_id,
            "created_at": now,
            "note": "fixture",
        },
    ).lastrowid
    session.execute(
        db_utils.text(
            "INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (:device_id, :tag_id, :created_at)"
        ),
        {"device_id": "DEV-001", "tag_id": tag_id, "created_at": now},
    )
    event_id = session.execute(
        db_utils.text(
            "INSERT INTO mined_events (event_name, color, status, mined_at, note) "
            "VALUES (:event_name, :color, 'active', :mined_at, :note)"
        ),
        {
            "event_name": "Fixture Event",
            "color": "#ff5722",
            "mined_at": now,
            "note": "fixture event",
        },
    ).lastrowid
    session.execute(
        db_utils.text(
            "INSERT INTO mined_event_iocs (event_id, target, port) VALUES (:event_id, :target, :port)"
        ),
        {"event_id": event_id, "target": "198.51.100.7", "port": "8080"},
    )
    session.commit()
    return True


def run_smoke(db_path):
    source_db = Path(db_path).resolve()
    if not source_db.exists():
        raise FileNotFoundError(f"DB not found: {source_db}")

    with tempfile.TemporaryDirectory(prefix="apt_mining_regression_") as temp_dir:
        temp_db = Path(temp_dir) / source_db.name
        shutil.copyfile(source_db, temp_db)
        _point_runtime_db(temp_db)

        session = get_session_local()()
        try:
            fixture_seeded = _seed_minimal_dataset(session)
            alerts_resp = query_alerts(
                date_start=None,
                date_end=None,
                target_type=None,
                device_tags=None,
                threat_types=None,
                threat_levels=None,
                apt_tiers=None,
                hide_traced=True,
                hide_closed=True,
                keyword=None,
                alert_count_max=None,
                badges_filter=None,
                page=1,
                page_size=100,
                db=session,
            )
            candidates_resp = query_alert_candidates(
                date_start=None,
                date_end=None,
                target_type=None,
                device_tags=None,
                threat_types=None,
                threat_levels=None,
                apt_tiers=None,
                hide_traced=False,
                hide_closed=True,
                keyword=None,
                alert_count_max=None,
                badges_filter=None,
                target_kind="all",
                page=1,
                page_size=100,
                db=session,
            )

            batch_row = session.execute(
                db_utils.text("SELECT id FROM tag_batches ORDER BY id LIMIT 1")
            ).fetchone()
            if batch_row is None:
                raise RuntimeError("No tag batch available for restore smoke test.")
            batch_id = batch_row[0]
            batch_before = get_batch(batch_id, db=session)
            if "DEV-001" not in batch_before["devices"]:
                raise RuntimeError("Fixture batch is missing DEV-001 before restore test.")

            remove_result = remove_devices_from_batch(
                batch_id,
                {"devices": ["DEV-001"]},
                db=session,
            )
            if remove_result.get("removed_count", 0) < 1:
                raise RuntimeError("Expected DEV-001 to be removed from fixture batch.")

            batch_after_remove = get_batch(batch_id, db=session)
            if "DEV-001" in batch_after_remove["devices"]:
                raise RuntimeError("DEV-001 still present in batch detail after removal.")

            restore_result = restore_batch(batch_id, db=session)
            if restore_result.get("restored_count", 0) < 1:
                raise RuntimeError("Expected restore_batch to re-attach at least one device tag.")

            batch_after_restore = get_batch(batch_id, db=session)
            if "DEV-001" not in batch_after_restore["devices"]:
                raise RuntimeError("DEV-001 was not restored into the fixture batch.")

            restored_link = session.execute(
                db_utils.text(
                    "SELECT 1 FROM device_tags dt "
                    "JOIN tags t ON t.id = dt.tag_id "
                    "WHERE t.batch_id = :batch_id AND dt.device_id = :device_id"
                ),
                {"batch_id": batch_id, "device_id": "DEV-001"},
            ).fetchone()
            if restored_link is None:
                raise RuntimeError("Restored batch is missing the expected device-tag link.")

            candidate_items = candidates_resp["items"]
            if not candidate_items:
                raise RuntimeError("No candidate items returned in smoke regression.")
            first_candidate = candidate_items[0]
            required_candidate_fields = {
                "candidate_priority",
                "candidate_priority_label",
                "target_kind_label",
                "heat_summary",
                "candidate_focus",
                "candidate_summary",
                "trace_status_label",
                "sort_signals",
            }
            missing_fields = sorted(required_candidate_fields - set(first_candidate.keys()))
            if missing_fields:
                raise RuntimeError(f"Candidate item missing fields: {missing_fields}")
            meta_scope = candidates_resp["meta"].get("candidate_scope", {})
            if "rule_catalog" not in meta_scope or "sort_logic" not in meta_scope:
                raise RuntimeError("Candidate meta is missing rule catalog or sort logic.")

            first_alert = session.execute(db_utils.text("SELECT * FROM alerts ORDER BY id LIMIT 1")).fetchone()
            if first_alert is None:
                raise RuntimeError("No alerts available for dedupe smoke test.")

            alert_item = dict(first_alert._mapping)
            alert_item.pop("id", None)
            duplicate_inserted, _ = _insert_alert(session, dict(alert_item))

            variant = dict(alert_item)
            variant["last_alert_time"] = "2099-01-01 00:00:01"
            variant["content_hash"] = compute_alert_content_hash(variant)
            variant["unique_hash"] = variant["content_hash"]
            variant_inserted, _ = _insert_alert(session, variant)
            session.rollback()
        finally:
            session.close()
            if db_utils._engine is not None:
                db_utils._engine.dispose()

    return {
        "fixture_seeded": fixture_seeded,
        "alerts_total": alerts_resp["total"],
        "candidates_total": candidates_resp["total"],
        "candidate_meta_keys": sorted(candidates_resp["meta"].keys()),
        "first_candidate_priority": first_candidate["candidate_priority"],
        "first_candidate_target_kind": first_candidate["target_kind"],
        "duplicate_inserted": duplicate_inserted,
        "variant_inserted": variant_inserted,
    }


def main():
    parser = argparse.ArgumentParser(description="Run a minimal regression smoke test.")
    parser.add_argument("--db", default="apt_mining.db", help="Path to the source sqlite db file.")
    args = parser.parse_args()
    result = run_smoke(args.db)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
