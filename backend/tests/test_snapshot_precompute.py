import os
import sys
import json
import unittest

from sqlalchemy import text
from fastapi.testclient import TestClient

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.main import app
from backend.services.snapshot_builder import (
    rebuild_candidate_snapshots,
    get_active_snapshot_version,
    patch_snapshot_for_event,
    patch_snapshot_for_trace,
    patch_snapshot_for_device_tags,
)
from backend.utils.db import get_engine, init_db, get_session_local


class TestSnapshotPrecompute(unittest.TestCase):
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
                "event_followups",
                "mined_event_iocs",
                "mined_event_devices",
                "mined_events",
                "traced_targets",
                "device_tags",
                "tags",
                "tag_batches",
                "alerts",
            ):
                try:
                    db.execute(text(f"DELETE FROM {table}"))
                except Exception:
                    pass
            db.commit()

    def _insert_alert(self, db, **kwargs):
        defaults = {
            "device_id": "TEST-PC-001",
            "source_ip": "10.0.0.1",
            "target": "evil.com",
            "port": "443",
            "target_type": "domain",
            "threat_type": "apt",
            "threat_level": "high",
            "std_apt_org": "oceanlotus",
            "apt_org": "海莲花",
            "apt_org_tier": "一级",
            "vendors": "厂商A",
            "alert_count": 5,
            "first_alert_time": "2026-04-29 09:00:00",
            "last_alert_time": "2026-04-29 18:00:00",
            "content_hash": "hash_" + str(os.urandom(4).hex()),
            "source_file": "test.xlsx",
            "imported_at": "2026-05-14T00:00:00",
        }
        defaults.update(kwargs)
        cols = ", ".join(defaults.keys())
        placeholders = ", ".join(f":{k}" for k in defaults.keys())
        cursor = db.execute(
            text(f"INSERT INTO alerts ({cols}) VALUES ({placeholders})"),
            defaults,
        )
        db.commit()
        return cursor.lastrowid

    # --- Full rebuild tests ---

    def test_full_rebuild_creates_rows(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, device_id="PC-001", target="evil.com", port="443")
            self._insert_alert(db, device_id="PC-002", target="evil2.com", port="80")
            result = rebuild_candidate_snapshots(db)
            self.assertTrue(result["ok"])
            self.assertEqual(result["row_count"], 2)

            version = get_active_snapshot_version(db)
            self.assertIsNotNone(version)

            rows = db.execute(text(
                "SELECT * FROM alert_candidate_snapshots WHERE snapshot_version = :v"
            ), {"v": version}).fetchall()
            self.assertEqual(len(rows), 2)

    def test_full_rebuild_stores_badges_json(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, std_apt_org="oceanlotus")
            rebuild_candidate_snapshots(db)
            version = get_active_snapshot_version(db)
            row = db.execute(text(
                "SELECT badges_json FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            self.assertIsNotNone(row)
            badges = json.loads(row[0])
            self.assertIsInstance(badges, list)

    def test_full_rebuild_stores_device_tags_json(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, device_id="TAGGED-PC")
            # Add a tag
            cursor = db.execute(text(
                "INSERT INTO tags (name, color, is_permanent, created_at) VALUES (:name, :color, 1, :now)"
            ), {"name": "重点设备", "color": "#F56C6C", "now": "2026-01-01T00:00:00"})
            tag_id = cursor.lastrowid
            db.execute(text(
                "INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (:did, :tid, :now)"
            ), {"did": "TAGGED-PC", "tid": tag_id, "now": "2026-01-01T00:00:00"})
            db.commit()

            rebuild_candidate_snapshots(db)
            version = get_active_snapshot_version(db)
            row = db.execute(text(
                "SELECT device_tags_json FROM alert_candidate_snapshots WHERE snapshot_version = :v AND device_id = 'TAGGED-PC'"
            ), {"v": version}).fetchone()
            tags = json.loads(row[0])
            self.assertEqual(len(tags), 1)
            self.assertEqual(tags[0]["name"], "重点设备")

    def test_full_rebuild_creates_badge_subtable(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, std_apt_org="oceanlotus")
            rebuild_candidate_snapshots(db)
            version = get_active_snapshot_version(db)
            badges = db.execute(text(
                "SELECT badge_name FROM alert_candidate_snapshot_badges WHERE snapshot_version = :v"
            ), {"v": version}).fetchall()
            badge_names = {r[0] for r in badges}
            self.assertIn("apt_dict", badge_names)

    # --- Snapshot query path tests ---

    def test_snapshot_query_returns_snapshot_status(self):
        with self.SessionLocal() as db:
            self._insert_alert(db)
            rebuild_candidate_snapshots(db)

        resp = self.client.get("/api/alert-candidates?page_size=100")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["meta"]["snapshot_status"], "snapshot")
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["items"]), 1)

    def test_snapshot_query_date_filter(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, first_alert_time="2026-04-29 09:00:00")
            self._insert_alert(db, device_id="PC-002", target="other.com",
                               first_alert_time="2026-05-01 09:00:00", content_hash="h2")
            rebuild_candidate_snapshots(db)

        resp = self.client.get("/api/alert-candidates?date_start=2026-04-29&date_end=2026-04-29&page_size=100")
        data = resp.json()
        self.assertEqual(data["total"], 1)

    def test_snapshot_query_keyword_filter(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, device_id="LAPTOP-ABC", target="evil.com")
            self._insert_alert(db, device_id="SRV-XYZ", target="good.com", content_hash="h2")
            rebuild_candidate_snapshots(db)

        resp = self.client.get("/api/alert-candidates?keyword=LAPTOP&page_size=100")
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["device_id"], "LAPTOP-ABC")

    def test_snapshot_rebuild_keeps_distinct_alert_rows_for_same_ioc(self):
        with self.SessionLocal() as db:
            self._insert_alert(
                db,
                device_id="WIN-yangjiu",
                source_ip="192.168.10.89",
                target="webex.cisco-meeting.xyz",
                port="6666",
                threat_type="APT,远控木马,恶意软件",
                threat_level="高",
                std_apt_org="dukes",
                apt_org="Lazarus",
                apt_org_tier="三级",
                alert_count=111,
                first_alert_time="2026-05-10 22:00:00",
                last_alert_time="2026-05-10 23:00:00",
                content_hash="hash-shared-1",
            )
            self._insert_alert(
                db,
                device_id="WIN-yangjiu",
                source_ip="192.168.10.89",
                target="webex.cisco-meeting.xyz",
                port="6666",
                threat_type="APT,远控木马,恶意软件",
                threat_level="高",
                std_apt_org="dukes",
                apt_org="Lazarus",
                apt_org_tier="三级",
                alert_count=222,
                first_alert_time="2026-05-11 22:44:00",
                last_alert_time="2026-05-11 23:59:00",
                content_hash="hash-shared-2",
            )
            result = rebuild_candidate_snapshots(db)
            self.assertTrue(result["ok"])
            version = get_active_snapshot_version(db)
            rows = db.execute(text(
                "SELECT first_alert_time, last_alert_time FROM alert_candidate_snapshots "
                "WHERE snapshot_version = :v AND device_id = 'WIN-yangjiu' "
                "AND target = 'webex.cisco-meeting.xyz' AND port = '6666' "
                "ORDER BY first_alert_time"
            ), {"v": version}).fetchall()
            self.assertEqual(
                [(row[0], row[1]) for row in rows],
                [
                    ("2026-05-10 22:00:00", "2026-05-10 23:00:00"),
                    ("2026-05-11 22:44:00", "2026-05-11 23:59:00"),
                ],
            )

        resp = self.client.get("/api/alert-candidates?date_start=2026-05-11&date_end=2026-05-11&page_size=100")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["first_alert_time"], "2026-05-11 22:44:00")
        self.assertEqual(data["items"][0]["last_alert_time"], "2026-05-11 23:59:00")

    def test_snapshot_query_sort(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, device_id="LOW-SCORE", threat_type="normal", target="a.com")
            self._insert_alert(db, device_id="HIGH-SCORE", threat_type="apt", target="b.com", content_hash="h2")
            rebuild_candidate_snapshots(db)

        resp = self.client.get("/api/alert-candidates?sort_by=candidate_score&sort_order=desc&page_size=100")
        data = resp.json()
        self.assertEqual(data["items"][0]["device_id"], "HIGH-SCORE")

    def test_snapshot_query_badges_filter(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, std_apt_org="oceanlotus")
            self._insert_alert(db, device_id="PC-NO-BADGE", target="clean.com",
                               threat_type="normal", std_apt_org="", content_hash="h2")
            rebuild_candidate_snapshots(db)

        resp = self.client.get("/api/alert-candidates?badges_filter=apt_dict&page_size=100")
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["std_apt_org"], "oceanlotus")

    # --- Incremental update tests ---

    def test_patch_for_event_creation(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, target="evil.com", port="443")
            rebuild_candidate_snapshots(db)
            version = get_active_snapshot_version(db)

            # Get score before event
            row = db.execute(text(
                "SELECT event_json, candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            self.assertIsNone(row[0])
            score_before = row[1]

            # Create event
            cursor = db.execute(text(
                "INSERT INTO mined_events (event_name, color, status, mined_at) VALUES (:name, :color, :status, :now)"
            ), {"name": "测试事件", "color": "#FF5722", "status": "active", "now": "2026-05-14T00:00:00"})
            event_id = cursor.lastrowid
            db.execute(text(
                "INSERT INTO mined_event_iocs (event_id, target, port) VALUES (:eid, :target, :port)"
            ), {"eid": event_id, "target": "evil.com", "port": "443"})
            db.commit()

            # Patch
            patch_snapshot_for_event(db, event_id)

            # Verify event is now present
            row = db.execute(text(
                "SELECT event_json, event_status, candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            event_info = json.loads(row[0])
            self.assertIsNotNone(event_info)
            self.assertEqual(event_info["event_name"], "测试事件")
            self.assertEqual(row[1], "active")
            # Score should have increased by 6 (event bonus)
            self.assertEqual(row[2], score_before + 6)

    def test_patch_for_event_deletion(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, target="evil.com", port="443")
            rebuild_candidate_snapshots(db)
            version = get_active_snapshot_version(db)

            # Create event
            cursor = db.execute(text(
                "INSERT INTO mined_events (event_name, color, status, mined_at) VALUES (:name, :color, :status, :now)"
            ), {"name": "测试事件", "color": "#FF5722", "status": "active", "now": "2026-05-14T00:00:00"})
            event_id = cursor.lastrowid
            db.execute(text(
                "INSERT INTO mined_event_iocs (event_id, target, port) VALUES (:eid, :target, :port)"
            ), {"eid": event_id, "target": "evil.com", "port": "443"})
            db.commit()
            patch_snapshot_for_event(db, event_id)

            # Get score with event
            row = db.execute(text(
                "SELECT candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            score_with_event = row[0]

            # Delete event
            db.execute(text("DELETE FROM mined_events WHERE id = :id"), {"id": event_id})
            db.commit()

            # Simulate what delete_event does: patch with event_info=None
            from backend.api.events import _patch_snapshot_for_event_deletion
            _patch_snapshot_for_event_deletion(db, [("evil.com", "443")], [])

            # Verify event removed
            row = db.execute(text(
                "SELECT event_json, candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            self.assertIsNone(row[0])
            self.assertLess(row[1], score_with_event)

    def test_patch_for_trace(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, target="evil.com", port="443")
            rebuild_candidate_snapshots(db)
            version = get_active_snapshot_version(db)

            # Get score before trace
            row = db.execute(text(
                "SELECT trace_status, ioc_note, candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            self.assertEqual(row[0], "none")
            self.assertIsNone(row[1])
            score_before = row[2]

            # Add IOC note
            db.execute(text(
                "INSERT INTO traced_targets (target, port, traced_at, note) VALUES (:target, :port, :at, :note)"
            ), {"target": "evil.com", "port": "443", "at": "2026-05-14T00:00:00", "note": "C2服务器"})
            db.commit()

            patch_snapshot_for_trace(db, "evil.com", "443")

            # Verify trace is now present and score decreased
            row = db.execute(text(
                "SELECT trace_status, ioc_note, candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            self.assertEqual(row[0], "active")
            self.assertEqual(row[1], "C2服务器")
            # Active trace gives -12 deduction
            self.assertEqual(row[2], score_before - 12)

    def test_patch_for_device_tags(self):
        with self.SessionLocal() as db:
            self._insert_alert(db, device_id="LAPTOP-001", target="evil.com")
            rebuild_candidate_snapshots(db)
            version = get_active_snapshot_version(db)

            # Verify no tags initially
            row = db.execute(text(
                "SELECT device_tags_json, candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            self.assertEqual(json.loads(row[0]), [])
            score_before = row[1]

            # Add tag
            cursor = db.execute(text(
                "INSERT INTO tags (name, color, is_permanent, created_at) VALUES (:name, :color, 1, :now)"
            ), {"name": "重点设备", "color": "#F56C6C", "now": "2026-01-01T00:00:00"})
            tag_id = cursor.lastrowid
            db.execute(text(
                "INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (:did, :tid, :now)"
            ), {"did": "LAPTOP-001", "tid": tag_id, "now": "2026-01-01T00:00:00"})
            db.commit()

            patch_snapshot_for_device_tags(db, ["LAPTOP-001"])

            # Verify tag is now present
            row = db.execute(text(
                "SELECT device_tags_json, candidate_score FROM alert_candidate_snapshots WHERE snapshot_version = :v LIMIT 1"
            ), {"v": version}).fetchone()
            tags = json.loads(row[0])
            self.assertEqual(len(tags), 1)
            self.assertEqual(tags[0]["name"], "重点设备")
            # Tag gives +2 score
            self.assertEqual(row[1], score_before + 2)

    # --- Consistency tests ---

    def test_snapshot_response_format_matches_live(self):
        """Verify snapshot response has all expected fields."""
        with self.SessionLocal() as db:
            self._insert_alert(db, std_apt_org="oceanlotus", threat_type="apt")
            rebuild_candidate_snapshots(db)

        resp = self.client.get("/api/alert-candidates?page_size=10")
        data = resp.json()
        item = data["items"][0]

        # Check all expected fields exist
        expected_fields = [
            "id", "device_id", "source_ip", "target", "port",
            "threat_type", "threat_level", "std_apt_org", "apt_org",
            "alert_count", "first_alert_time", "last_alert_time",
            "badges", "device_tags", "event", "traced",
            "candidate_rule_ids", "candidate_reasons", "candidate_score",
            "candidate_priority", "heat", "trace_status", "event_status",
            "ioc_note", "target_kind", "target_kind_label",
        ]
        for field in expected_fields:
            self.assertIn(field, item, f"Missing field: {field}")

        # Check nested structures
        self.assertIsInstance(item["badges"], list)
        self.assertIsInstance(item["device_tags"], list)
        self.assertIsInstance(item["candidate_priority"], dict)
        self.assertIsInstance(item["heat"], dict)
        self.assertIsInstance(item["candidate_rule_ids"], list)
        self.assertIsInstance(item["candidate_reasons"], list)

    # --- Performance sanity ---

    def test_snapshot_query_is_fast(self):
        """Snapshot query should return in under 1 second for small dataset."""
        import time
        with self.SessionLocal() as db:
            for i in range(50):
                self._insert_alert(
                    db,
                    device_id=f"PC-{i:04d}",
                    target=f"target{i}.com",
                    content_hash=f"perf_hash_{i}",
                )
            rebuild_candidate_snapshots(db)

        start = time.time()
        resp = self.client.get("/api/alert-candidates?page_size=100")
        elapsed = time.time() - start
        self.assertEqual(resp.status_code, 200)
        self.assertLess(elapsed, 1.0, f"Snapshot query took {elapsed:.2f}s, expected < 1s")


if __name__ == "__main__":
    unittest.main()
