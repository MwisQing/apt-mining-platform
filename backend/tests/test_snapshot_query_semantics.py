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
            for table in ("alerts", "traced_targets", "tags", "device_tags", "audit_log"):
                try:
                    db.execute(text(f"DELETE FROM {table}"))
                except Exception:
                    pass
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

    def test_returns_live_candidates_without_snapshot_versions(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES (:device_id, :source_ip, :target, :port, :target_type, :threat_type, :threat_level, "
                ":std_apt_org, :apt_org, :apt_org_tier, :vendors, :first_alert_time, :last_alert_time, :alert_count, "
                ":content_hash, :source_file, :imported_at, :unique_hash)"
            ), {
                "device_id": "DEV-LIVE",
                "source_ip": "10.0.0.8",
                "target": "live.example.com",
                "port": "443",
                "target_type": "domain",
                "threat_type": "apt",
                "threat_level": "high",
                "std_apt_org": "oceanlotus",
                "apt_org": "OceanLotus",
                "apt_org_tier": "一线",
                "vendors": "VendorA",
                "first_alert_time": "2026-05-01 09:00:00",
                "last_alert_time": "2026-05-01 10:00:00",
                "alert_count": 3,
                "content_hash": "hash-live-1",
                "source_file": "fixture.xlsx",
                "imported_at": "2026-05-01 10:10:00",
                "unique_hash": "unique-live-1",
            })
            db.commit()

        response = self._call_query(date_start="2026-05-01", date_end="2026-05-01")
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["target"], "live.example.com")
        self.assertIn("filter_options", response)
        self.assertNotEqual(response["meta"].get("snapshot_status"), "building")

    def test_ignores_snapshot_rows_and_reads_live_alerts(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES ('DEV-A', '10.0.0.9', 'active.example.com', '443', 'domain', 'apt', 'high', "
                "'oceanlotus', 'OceanLotus', '一线', 'VendorA', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 2, "
                "'hash-active', 'fixture.xlsx', '2026-05-01 10:10:00', 'unique-active')"
            ))
            db.commit()

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

    def test_meta_uses_live_status_after_snapshot_removal(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES ('DEV-A', '10.0.0.10', 'live-meta.example.com', '443', 'domain', 'apt', 'high', "
                "'oceanlotus', 'OceanLotus', '一线', 'VendorA', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 1, "
                "'hash-meta', 'fixture.xlsx', '2026-05-01 10:10:00', 'unique-meta')"
            ))
            db.commit()

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
        self.assertEqual(response["meta"]["snapshot_status"], "live")
        self.assertNotIn("snapshot_rebuilding", response["meta"])
        self.assertEqual(response["total"], 1)


if __name__ == "__main__":
    unittest.main()
