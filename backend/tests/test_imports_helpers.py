import json
import os
import tempfile
import unittest

from backend.api import imports
from backend.services.alert_workbench import compute_alert_content_hash


class ImportHelpersTestCase(unittest.TestCase):
    def test_resolve_row_status_filters_supports_issue_group(self):
        self.assertEqual(
            imports._resolve_row_status_filters(status=None, status_group="issues"),
            ("raw_only", "failed"),
        )

    def test_resolve_row_status_filters_prefers_explicit_status(self):
        self.assertEqual(
            imports._resolve_row_status_filters(status="skipped_duplicate", status_group="issues"),
            ("skipped_duplicate",),
        )

    def test_build_failure_export_rows_includes_key_columns(self):
        rows = [
            {
                "sheet_name": "Sheet1",
                "excel_row_number": 7,
                "parse_status": "skipped_duplicate",
                "parse_error": None,
                "raw_json": json.dumps(
                    {"设备ID": "DEV-01", "外联目标": "evil.example", "端口": "443"},
                    ensure_ascii=False,
                ),
                "normalized_json": json.dumps(
                    {"device_id": "DEV-01", "target": "evil.example", "port": "443"},
                    ensure_ascii=False,
                ),
            }
        ]

        exported = imports._build_failure_export_rows(rows)

        self.assertEqual(exported[0]["device_id"], "DEV-01")
        self.assertEqual(exported[0]["target"], "evil.example")
        self.assertEqual(exported[0]["port"], "443")
        self.assertEqual(exported[0]["status"], "skipped_duplicate")

    def test_should_run_vacuum_only_when_reclaim_is_material(self):
        self.assertFalse(
            imports._should_run_vacuum(page_size=4096, freelist_count=10, page_count=1000)
        )
        self.assertTrue(
            imports._should_run_vacuum(page_size=4096, freelist_count=9000, page_count=10000)
        )

    def test_rebuild_import_row_updates_repairs_uploaded_rows(self):
        rows = [
            {
                "id": 1,
                "sheet_name": "Sheet1",
                "excel_row_number": 2,
                "raw_json": json.dumps({"设备ID": "DEV-01", "外联目标": "evil.example", "告警时间": "2026-05-07 00:00:00"}, ensure_ascii=False),
            },
            {
                "id": 2,
                "sheet_name": "Sheet1",
                "excel_row_number": 3,
                "raw_json": json.dumps({"设备ID": "DEV-01", "外联目标": "evil.example", "告警时间": "2026-05-07 00:00:00"}, ensure_ascii=False),
            },
            {
                "id": 3,
                "sheet_name": "Sheet1",
                "excel_row_number": 4,
                "raw_json": json.dumps({"设备ID": "", "外联目标": "", "告警时间": ""}, ensure_ascii=False),
            },
        ]
        parsed_alert_map = {
            1: {"alert_id": 101},
        }

        updates, stats = imports._rebuild_import_row_updates_for_repair(
            rows,
            parsed_alert_map=parsed_alert_map,
            existing_hashes=set(),
        )

        self.assertEqual(updates[0]["parse_status"], "parsed")
        self.assertEqual(updates[0]["alert_id"], 101)
        self.assertEqual(updates[1]["parse_status"], "skipped_duplicate")
        self.assertEqual(updates[2]["parse_status"], "raw_only")
        self.assertEqual(stats["parsed"], 2)
        self.assertEqual(stats["raw_only"], 1)
        self.assertEqual(stats["failed"], 0)

    def test_content_hash_changes_when_time_changes(self):
        base = {
            "device_id": "DEV-01",
            "first_alert_time": "2026-05-07 00:00:00",
            "last_alert_time": "2026-05-07 00:00:00",
            "source_ip": "SRC-1",
            "target": "evil.example",
            "target_type": "domain",
            "port": "443",
            "threat_type": "apt",
            "threat_level": "high",
            "std_apt_org": "apt-x",
            "apt_org": "APT X",
            "apt_org_tier": "一级",
            "alert_count": 1,
            "vendors": "VendorA",
            "protocol": "tcp",
            "intel_tags": "c2",
            "dns_resolved_ip": None,
            "down_traffic": 0,
            "up_traffic": 0,
            "asset_type": None,
        }
        changed_time = dict(base)
        changed_time["last_alert_time"] = "2026-05-07 00:00:01"

        self.assertNotEqual(
            compute_alert_content_hash(base),
            compute_alert_content_hash(changed_time),
        )

    def test_delete_import_cleanup_only_truncates_wal(self):
        class FakeRawConnection:
            def __init__(self):
                self.commands = []

            def execute(self, sql):
                self.commands.append(sql)

        raw_conn = FakeRawConnection()

        imports._checkpoint_after_import_delete(raw_conn)

        self.assertEqual(raw_conn.commands, ["PRAGMA wal_checkpoint(TRUNCATE)"])


if __name__ == "__main__":
    unittest.main()
