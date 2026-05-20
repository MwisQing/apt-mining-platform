import os
import sys
import unittest

from sqlalchemy import text

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.api import alerts
from backend.services.snapshot_builder import (
    patch_snapshot_for_device_tags,
    patch_snapshot_for_event,
    patch_snapshot_for_trace,
)
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
            for table in ("mined_event_iocs", "mined_event_devices", "event_followups", "mined_events"):
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
            "apt_orgs": None,
            "ports": None,
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

    def test_live_query_keeps_distinct_alert_rows_for_same_ioc(self):
        with self.SessionLocal() as db:
            for idx, first_alert_time in enumerate(("2026-05-01 09:00:00", "2026-05-02 09:00:00"), start=1):
                db.execute(text(
                    "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                    "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                    "content_hash, source_file, imported_at, unique_hash) "
                    "VALUES (:device_id, :source_ip, :target, :port, :target_type, :threat_type, :threat_level, "
                    ":std_apt_org, :apt_org, :apt_org_tier, :vendors, :first_alert_time, :last_alert_time, :alert_count, "
                    ":content_hash, :source_file, :imported_at, :unique_hash)"
                ), {
                    "device_id": "DEV-SHARED",
                    "source_ip": "10.0.0.88",
                    "target": "shared.example.com",
                    "port": "6666",
                    "target_type": "domain",
                    "threat_type": "apt,远控木马",
                    "threat_level": "high",
                    "std_apt_org": "dukes",
                    "apt_org": "Lazarus",
                    "apt_org_tier": "三级",
                    "vendors": "VendorA",
                    "first_alert_time": first_alert_time,
                    "last_alert_time": first_alert_time.replace("09:00:00", "10:00:00"),
                    "alert_count": 10 + idx,
                    "content_hash": f"hash-shared-{idx}",
                    "source_file": "fixture.xlsx",
                    "imported_at": "2026-05-14 10:10:00",
                    "unique_hash": f"unique-shared-{idx}",
                })
            db.commit()

        response = self._call_query(
            date_start="2026-05-01",
            date_end="2026-05-02",
            keyword="DEV-SHARED",
        )
        self.assertEqual(response["total"], 2)
        self.assertEqual(
            [item["first_alert_time"] for item in response["items"]],
            ["2026-05-02 09:00:00", "2026-05-01 09:00:00"],
        )

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

    def test_meta_uses_snapshot_status_when_active_snapshot_exists(self):
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
        self.assertEqual(response["meta"]["snapshot_status"], "snapshot")
        self.assertNotIn("snapshot_rebuilding", response["meta"])
        self.assertEqual(response["total"], 1)

    def test_snapshot_query_returns_patched_event_tag_and_ioc_note(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO alerts (device_id, source_ip, target, port, target_type, threat_type, threat_level, "
                "std_apt_org, apt_org, apt_org_tier, vendors, first_alert_time, last_alert_time, alert_count, "
                "content_hash, source_file, imported_at, unique_hash) "
                "VALUES ('DEV-REFRESH', '10.0.0.11', 'refresh.example.com', '443', 'domain', 'apt', 'high', "
                "'oceanlotus', 'OceanLotus', '一线', 'VendorA', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 1, "
                "'hash-refresh', 'fixture.xlsx', '2026-05-01 10:10:00', 'unique-refresh')"
            ))
            db.commit()

        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, status) "
                "VALUES ('alert_candidates', 'v_stale', 'ready')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, target_kind, target_kind_label"
                ") VALUES ("
                "'v_stale', 'DEV-REFRESH', 'refresh.example.com', '443', 99, 'p1', '高优先', "
                "'2026-05-11T00:00:00', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 'domain', '域名视角'"
                ")"
            ))
            tag_id = db.execute(text(
                "INSERT INTO tags (name, color, is_permanent, created_at) "
                "VALUES ('重点设备', '#F56C6C', 1, '2026-05-14T00:00:00')"
            )).lastrowid
            db.execute(text(
                "INSERT INTO device_tags (device_id, tag_id, created_at) "
                "VALUES ('DEV-REFRESH', :tag_id, '2026-05-14T00:00:00')"
            ), {"tag_id": tag_id})
            event_id = db.execute(text(
                "INSERT INTO mined_events (event_name, color, note, status, mined_at) "
                "VALUES ('刷新事件', '#409EFF', 'event note', 'open', '2026-05-14T00:00:00')"
            )).lastrowid
            db.execute(text(
                "INSERT INTO mined_event_iocs (event_id, target, port) "
                "VALUES (:event_id, 'refresh.example.com', '443')"
            ), {"event_id": event_id})
            db.execute(text(
                "INSERT INTO traced_targets (target, port, traced_at, note) "
                "VALUES ('refresh.example.com', '443', '2026-05-14T00:00:00', 'IOC刷新备注')"
            ))
            patch_snapshot_for_event(db, event_id)
            patch_snapshot_for_trace(db, "refresh.example.com", "443")
            patch_snapshot_for_device_tags(db, ["DEV-REFRESH"])
            db.commit()

        response = self._call_query(date_start="2026-05-01", date_end="2026-05-01")
        self.assertEqual(response["meta"]["snapshot_status"], "snapshot")
        self.assertEqual(response["total"], 1)
        item = response["items"][0]
        self.assertEqual(item["ioc_note"], "IOC刷新备注")
        self.assertEqual(item["event"]["event_name"], "刷新事件")
        self.assertEqual([tag["name"] for tag in item["device_tags"]], ["重点设备"])

    def test_snapshot_query_overlays_live_relations_when_snapshot_is_stale(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, status) "
                "VALUES ('alert_candidates', 'v_stale_relations', 'ready')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, target_kind, target_kind_label"
                ") VALUES ("
                "'v_stale_relations', 'DEV-STALE', 'stale-event.example.com', '443', 50, 'p3', '观察', "
                "'2026-05-11T00:00:00', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 'domain', '域名视角'"
                ")"
            ))
            tag_id = db.execute(text(
                "INSERT INTO tags (name, color, is_permanent, created_at) "
                "VALUES ('事件设备', '#409EFF', 1, '2026-05-15T00:00:00')"
            )).lastrowid
            db.execute(text(
                "INSERT INTO device_tags (device_id, tag_id, created_at) "
                "VALUES ('DEV-STALE', :tag_id, '2026-05-15T00:00:00')"
            ), {"tag_id": tag_id})
            event_id = db.execute(text(
                "INSERT INTO mined_events (event_name, color, note, status, mined_at) "
                "VALUES ('快照外事件', '#67C23A', 'created after snapshot', 'active', '2026-05-15T00:00:00')"
            )).lastrowid
            db.execute(text(
                "INSERT INTO mined_event_iocs (event_id, target, port) "
                "VALUES (:event_id, 'stale-event.example.com', '443')"
            ), {"event_id": event_id})
            db.execute(text(
                "INSERT INTO traced_targets (target, port, traced_at, note) "
                "VALUES ('stale-event.example.com', '443', '2026-05-15T00:00:00', '实时备注')"
            ))
            db.commit()

        response = self._call_query(date_start="2026-05-01", date_end="2026-05-01")
        self.assertEqual(response["meta"]["snapshot_status"], "snapshot")
        self.assertEqual(response["total"], 1)
        item = response["items"][0]
        self.assertEqual(item["event"]["event_name"], "快照外事件")
        self.assertEqual(item["event_status"], "active")
        self.assertEqual([tag["name"] for tag in item["device_tags"]], ["事件设备"])
        self.assertEqual(item["ioc_note"], "实时备注")
        self.assertEqual(item["trace_status"], "active")


    def test_snapshot_device_tag_filter_uses_live_tags_when_snapshot_subtable_is_stale(self):
        with self.SessionLocal() as db:
            db.execute(text(
                "INSERT INTO snapshot_build_meta (snapshot_type, active_version, status) "
                "VALUES ('alert_candidates', 'v_stale_tags', 'ready')"
            ))
            db.execute(text(
                "INSERT INTO alert_candidate_snapshots ("
                "snapshot_version, device_id, target, port, candidate_score, candidate_priority, "
                "candidate_priority_label, updated_at, first_alert_time, last_alert_time, target_kind, target_kind_label"
                ") VALUES ("
                "'v_stale_tags', 'DEV-LIVE-TAG', 'tagged.example.com', '443', 50, 'p3', 'observe', "
                "'2026-05-16T00:00:00', '2026-05-01 09:00:00', '2026-05-01 10:00:00', 'domain', 'domain'"
                ")"
            ))
            tag_id = db.execute(text(
                "INSERT INTO tags (name, color, is_permanent, created_at) "
                "VALUES ('Focus Device', '#F56C6C', 1, '2026-05-16T00:00:00')"
            )).lastrowid
            db.execute(text(
                "INSERT INTO device_tags (device_id, tag_id, created_at) "
                "VALUES ('DEV-LIVE-TAG', :tag_id, '2026-05-16T00:00:00')"
            ), {"tag_id": tag_id})
            db.commit()

        response = self._call_query(
            date_start="2026-05-01",
            date_end="2026-05-01",
            device_tags="Focus Device",
        )
        self.assertEqual(response["meta"]["snapshot_status"], "snapshot")
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["items"][0]["device_id"], "DEV-LIVE-TAG")
        self.assertEqual([tag["name"] for tag in response["items"][0]["device_tags"]], ["Focus Device"])
        self.assertIn("Focus Device", response["filter_options"]["device_tags"])


if __name__ == "__main__":
    unittest.main()
