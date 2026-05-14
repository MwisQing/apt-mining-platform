import os
import sys
import unittest

from sqlalchemy import text
from fastapi.testclient import TestClient

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.main import app
from backend.services.snapshot_builder import rebuild_candidate_snapshots
from backend.utils.db import get_engine, init_db, get_session_local


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

    def test_candidates_endpoint_returns_building_state_without_active_snapshot(self):
        response = self.client.get("/api/alert-candidates?page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["items"], [])
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["meta"]["snapshot_status"], "building")

    def test_candidates_endpoint_uses_active_snapshot_version_only(self):
        with self.SessionLocal() as db:
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
                "'v_active', 'DEV-A', 'active.example.com', '443', 99, 'p1', '高优先', "
                "'2026-05-11T00:00:00', '2026-05-11 09:00:00', '2026-05-11 10:00:00', "
                "'domain', '域名视角'"
                ")"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, "
                "target_kind, target_kind_label"
                ") VALUES ("
                "'v_building', 'DEV-B', 'building.example.com', '443', 10, 'p3', '观察', "
                "'2026-05-11T00:00:00', '2026-05-11 09:00:00', '2026-05-11 10:00:00', "
                "'domain', '域名视角'"
                ")"
            ))
            db.commit()

        response = self.client.get("/api/alert-candidates?page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        targets = [item["target"] for item in body["items"]]
        self.assertIn("active.example.com", targets)
        self.assertNotIn("building.example.com", targets)

    def test_badges_filter_uses_structured_badge_table(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, status) "
                "VALUES ('alert_candidates', 'v_active', 'ready')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "id, snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, "
                "target_kind, target_kind_label"
                ") VALUES ("
                "1, 'v_active', 'DEV-A', 'alpha.example.com', '443', 90, 'p1', '高优先', "
                "'2026-05-11T00:00:00', '2026-05-11 09:00:00', '2026-05-11 10:00:00', "
                "'domain', '域名视角'"
                ")"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "id, snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, "
                "target_kind, target_kind_label"
                ") VALUES ("
                "2, 'v_active', 'DEV-B', 'beta.example.com', '443', 80, 'p2', '中优先', "
                "'2026-05-11T00:00:00', '2026-05-11 09:00:00', '2026-05-11 10:00:00', "
                "'domain', '域名视角'"
                ")"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshot_badges (snapshot_version, snapshot_id, badge_name, badge_label, badge_color) "
                "VALUES ('v_active', 1, 'apt_dict', 'APT词典', 'red')"
            ))
            db.commit()

        response = self.client.get("/api/alert-candidates?badges_filter=apt_dict&page=1&page_size=50")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["target"], "alpha.example.com")

    def test_device_tag_filter_options_come_from_snapshot_tag_table(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, status) "
                "VALUES ('alert_candidates', 'v_active', 'ready')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "id, snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, "
                "target_kind, target_kind_label, threat_type, std_apt_org"
                ") VALUES ("
                "1, 'v_active', 'DEV-A', 'alpha.example.com', '443', 90, 'p1', '高优先', "
                "'2026-05-11T00:00:00', '2026-05-11 09:00:00', '2026-05-11 10:00:00', "
                "'domain', '域名视角', 'apt', 'oceanlotus'"
                ")"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshot_tags (snapshot_version, snapshot_id, tag_id, tag_name, tag_color) "
                "VALUES ('v_active', 1, 101, '重点设备', '#F56C6C')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshot_badges (snapshot_version, snapshot_id, badge_name, badge_label, badge_color) "
                "VALUES ('v_active', 1, 'apt_dict', 'APT词典', 'red')"
            ))
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
