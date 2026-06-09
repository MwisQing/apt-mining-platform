import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name):
    path = ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OpsDataGoScriptsTest(unittest.TestCase):
    def test_export_tables_exclude_excel_source_rows(self):
        export_mod = load_module("export_ops_data_go")

        self.assertIn("imports", export_mod.EXPORT_TABLES)
        self.assertIn("import_sheets", export_mod.EXPORT_TABLES)
        self.assertIn("alert_annotations", export_mod.EXPORT_TABLES)
        self.assertIn("mined_events", export_mod.EXPORT_TABLES)
        self.assertIn("traced_targets", export_mod.EXPORT_TABLES)
        self.assertIn("device_tags", export_mod.EXPORT_TABLES)
        self.assertIn("audit_log", export_mod.EXPORT_TABLES)
        self.assertIn("config", export_mod.EXPORT_TABLES)
        self.assertNotIn("alerts", export_mod.EXPORT_TABLES)
        self.assertNotIn("import_rows", export_mod.EXPORT_TABLES)

    def test_import_order_respects_foreign_keys(self):
        import_mod = load_module("import_ops_data_go")
        order = import_mod.IMPORT_TABLES

        self.assertLess(order.index("imports"), order.index("import_sheets"))
        self.assertGreater(order.index("alert_annotations"), order.index("import_sheets"))
        self.assertLess(order.index("tag_batches"), order.index("tags"))
        self.assertLess(order.index("tags"), order.index("device_tags"))
        self.assertLess(order.index("mined_events"), order.index("mined_event_devices"))
        self.assertLess(order.index("mined_events"), order.index("mined_event_iocs"))
        self.assertLess(order.index("mined_events"), order.index("event_followups"))
        self.assertNotIn("import_rows", order)

    def test_alert_annotation_match_columns_are_kept(self):
        import_mod = load_module("import_ops_data_go")
        row = {
            "id": 9,
            "device_id": "DEV-1",
            "content_hash": "abc123",
            "source_file": "old.xlsx",
            "analysis_status": "done",
            "is_focused": 1,
        }

        cleaned = import_mod.normalize_row_for_import("alert_annotations", row)

        self.assertEqual(cleaned["id"], 9)
        self.assertEqual(cleaned["content_hash"], "abc123")
        self.assertEqual(cleaned["analysis_status"], "done")
        self.assertEqual(cleaned["is_focused"], 1)
        self.assertEqual(cleaned["source_file"], "old.xlsx")


if __name__ == "__main__":
    unittest.main()
