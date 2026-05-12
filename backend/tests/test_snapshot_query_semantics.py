import os
import sys
import unittest

from sqlalchemy import text

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.api import alerts
from backend.utils.db import get_session_local, init_db


class TestSnapshotQuerySemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.SessionLocal = get_session_local()

    def setUp(self):
        with self.SessionLocal() as db:
            for table in (
                "alert_candidate_snapshot_tags",
                "alert_candidate_snapshot_badges",
                "alert_candidate_snapshots",
                "snapshot_build_meta",
            ):
                db.execute(text(f"DELETE FROM {table}"))
            db.commit()

    def _call_query(self, **kwargs):
        base = {
            "date_start": None,
            "date_end": None,
            "target_type": None,
            "device_tags": None,
            "exclude_device_tags": None,
            "threat_types": None,
            "threat_levels": None,
            "apt_tiers": None,
            "hide_traced": None,
            "hide_closed": None,
            "keyword": None,
            "alert_count_max": None,
            "badges_filter": None,
            "target_kind": "all",
            "sort_by": None,
            "sort_order": None,
            "page": 1,
            "page_size": 100,
        }
        base.update(kwargs)
        with self.SessionLocal() as db:
            base["db"] = db
            return alerts.query_alert_candidates(**base)

    def test_returns_building_state_when_no_active_snapshot_version(self):
        response = self._call_query(date_start="2026-05-01", date_end="2026-05-01")
        self.assertEqual(response["items"], [])
        self.assertEqual(response["total"], 0)
        self.assertEqual(response["meta"]["snapshot_status"], "building")

    def test_reads_only_active_snapshot_version(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, building_version, status) "
                "VALUES ('alert_candidates', 'v_active', 'v_building', 'ready')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, target_kind, target_kind_label"
                ") VALUES ("
                "'v_active', 'DEV-A', 'active.example.com', '443', 99, 'p1', '高优先', "
                "'2026-05-11T00:00:00', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 'domain', '域名视角'"
                ")"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, target_kind, target_kind_label"
                ") VALUES ("
                "'v_building', 'DEV-B', 'building.example.com', '443', 10, 'p3', '观察', "
                "'2026-05-11T00:00:00', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 'domain', '域名视角'"
                ")"
            ))
            db.commit()

        response = self._call_query(date_start="2026-05-01", date_end="2026-05-01")
        targets = [item["target"] for item in response["items"]]
        self.assertIn("active.example.com", targets)
        self.assertNotIn("building.example.com", targets)

    def test_meta_marks_rebuilding_without_hiding_active_snapshot(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, building_version, status) "
                "VALUES ('alert_candidates', 'v_active', 'v_building', 'building')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, target_kind, target_kind_label"
                ") VALUES ("
                "'v_active', 'DEV-A', 'active.example.com', '443', 99, 'p1', '高优先', "
                "'2026-05-11T00:00:00', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 'domain', '域名视角'"
                ")"
            ))
            db.commit()

        response = self._call_query(date_start="2026-05-01", date_end="2026-05-01")
        self.assertEqual(response["meta"]["snapshot_status"], "ready")
        self.assertTrue(response["meta"]["snapshot_rebuilding"])
        self.assertEqual(response["total"], 1)


if __name__ == "__main__":
    unittest.main()
