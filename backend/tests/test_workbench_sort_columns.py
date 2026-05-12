import os
import re
import unittest


ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
WORKBENCH_PATH = os.path.join(ROOT_DIR, "..", "frontend", "src", "views", "Workbench.vue")


class TestWorkbenchSortColumns(unittest.TestCase):
    def test_sortable_columns_render_sort_button(self):
        with open(WORKBENCH_PATH, "r", encoding="utf-8") as handle:
            content = handle.read()

        expected_columns = [
            "score",
            "device_id",
            "device_target_count",
            "source_ip",
            "source_ip_count",
            "target",
            "port",
            "device_alert_count",
            "threat_type",
            "std_apt_org",
            "analysis_status",
            "heat",
            "is_focused",
        ]

        for column_key in expected_columns:
            self.assertRegex(
                content,
                re.compile(rf'column-key="{re.escape(column_key)}"'),
                msg=f"Workbench 缺少 {column_key} 的表头排序按钮",
            )


if __name__ == "__main__":
    unittest.main()
