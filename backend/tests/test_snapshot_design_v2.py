import os
import sys
import unittest

from sqlalchemy import text
from fastapi.testclient import TestClient

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.main import app
from backend.services.snapshot_builder import rebuild_candidate_snapshots
from backend.utils.db import init_db, get_session_local


class TestSnapshotDesignV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.SessionLocal = get_session_local()

    def setUp(self):
        with self.SessionLocal() as db:
            for table in (
                "alert_candidate_snapshot_tags",
                "alert_candidate_snapshot_badges",
                "alert_candidate_snapshots",
                "snapshot_build_meta",
                "alerts",
            ):
                try:
                    db.execute(text(f"DELETE FROM {table}"))
                except Exception:
                    pass
            db.commit()

    def test_runtime_schema_creates_snapshot_tables(self):
        with self.SessionLocal() as db:
            tables = {
                row[0]
                for row in db.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
            }
        self.assertIn("alert_candidate_snapshots", tables)
        self.assertIn("alert_candidate_snapshot_badges", tables)
        self.assertIn("alert_candidate_snapshot_tags", tables)
        self.assertIn("snapshot_build_meta", tables)

    def test_candidates_endpoint_returns_live_state_without_active_snapshot(self):
        response = self.client.get("/api/alert-candidates?page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["meta"]["snapshot_status"], "live")

    def test_candidates_endpoint_reads_active_snapshot_when_snapshot_exists(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES ('DEV-LIVE', '10.0.0.1', 'live.example.com', '443', 'domain', 'apt', 'high', "
                "'oceanlotus', 'OceanLotus', '一线', 'VendorA', '2026-05-11 09:00:00', '2026-05-11 10:00:00', 3, "
                "'hash-live', 'fixture.xlsx', '2026-05-11 10:10:00', 'unique-live')"
            ))
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, building_version, status) "
                "VALUES ('alert_candidates', 'v_active', 'v_building', 'ready')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, "
                "target_kind, target_kind_label"
                ") VALUES ("
                "'v_active', 'DEV-SNAPSHOT', 'snapshot.example.com', '443', 99, 'p1', '高优先', "
                "'2026-05-11T00:00:00', '2026-05-11 09:00:00', '2026-05-11 10:00:00', "
                "'domain', '域名视角'"
                ")"
            ))
            db.commit()

        response = self.client.get("/api/alert-candidates?page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        targets = [item["target"] for item in body["items"]]
        self.assertIn("snapshot.example.com", targets)
        self.assertNotIn("live.example.com", targets)
        self.assertEqual(body["meta"]["snapshot_status"], "snapshot")

    def test_badges_filter_uses_live_badges(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES ('DEV-A', '10.0.0.1', 'alpha.example.com', '443', 'domain', 'apt', 'high', "
                "'oceanlotus', 'OceanLotus', '一线', 'VendorA', '2026-05-11 09:00:00', '2026-05-11 10:00:00', 3, "
                "'hash-a', 'fixture.xlsx', '2026-05-11 10:10:00', 'unique-a')"
            ))
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES ('DEV-B', '10.0.0.2', 'beta.example.com', '443', 'domain', 'normal', 'low', "
                "'', '', '', 'VendorB', '2026-05-11 09:00:00', '2026-05-11 10:00:00', 1, "
                "'hash-b', 'fixture.xlsx', '2026-05-11 10:10:00', 'unique-b')"
            ))
            db.commit()

        response = self.client.get("/api/alert-candidates?badges_filter=apt_dict&page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["target"], "alpha.example.com")

    def test_filter_options_come_from_live_relations(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES ('DEV-TAG', '10.0.0.1', 'alpha.example.com', '443', 'domain', 'apt', 'high', "
                "'oceanlotus', 'OceanLotus', '一线', 'VendorA', '2026-05-11 09:00:00', '2026-05-11 10:00:00', 3, "
                "'hash-tag', 'fixture.xlsx', '2026-05-11 10:10:00', 'unique-tag')"
            ))
            tag_id = db.execute(text(
                "INSERT INTO tags (name, color, is_permanent, created_at) "
                "VALUES ('重点设备', '#F56C6C', 1, '2026-05-14T00:00:00')"
            )).lastrowid
            db.execute(text(
                "INSERT INTO device_tags (device_id, tag_id, created_at) "
                "VALUES ('DEV-TAG', :tag_id, '2026-05-14T00:00:00')"
            ), {"tag_id": tag_id})
            db.commit()

        response = self.client.get("/api/alert-candidates?page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("重点设备", body["filter_options"]["device_tags"])
        self.assertIn("APT词典", body["filter_options"]["badges"])

    def test_snapshot_status_endpoint_reflects_meta(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, status, last_row_count) "
                "VALUES ('alert_candidates', 'v_active', 'ready', 12)"
            ))
            db.commit()
        response = self.client.get("/api/snapshots/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_version"], "v_active")
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["last_row_count"], 12)

    def test_rebuild_candidate_snapshots_creates_active_version(self):
        with self.SessionLocal() as db:
            result = rebuild_candidate_snapshots(db)
            self.assertTrue(result["ok"])
            meta = db.execute(text(
                "SELECT active_version, status, last_row_count FROM snapshot_build_meta WHERE snapshot_type = 'alert_candidates'"
            )).fetchone()
            self.assertIsNotNone(meta)
            self.assertTrue(meta[0])
            self.assertEqual(meta[1], "ready")
            self.assertGreaterEqual(meta[2], 0)
            count = db.execute(text(
                "SELECT COUNT(*) FROM alert_candidate_snapshots WHERE snapshot_version = :version"
            ), {"version": meta[0]}).scalar() or 0
            self.assertEqual(count, meta[2])


if __name__ == "__main__":
    unittest.main()
