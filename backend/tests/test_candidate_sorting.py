import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.api.alerts import SQL_CANDIDATE_SORTS, _candidate_sort_value, _normalize_candidate_sort


class TestCandidateSorting(unittest.TestCase):
    def test_sql_candidate_sorts_include_workbench_columns(self):
        self.assertIn("source_ip", SQL_CANDIDATE_SORTS)
        self.assertIn("analysis_status", SQL_CANDIDATE_SORTS)
        self.assertIn("is_focused", SQL_CANDIDATE_SORTS)

    def test_candidate_sort_value_supports_added_columns(self):
        item = {
            "source_ip": "10.0.0.8",
            "analysis_status": "已研判",
            "is_focused": 1,
        }
        self.assertEqual(_candidate_sort_value(item, "source_ip"), "10.0.0.8")
        self.assertEqual(_candidate_sort_value(item, "analysis_status"), "已研判")
        self.assertEqual(_candidate_sort_value(item, "is_focused"), 1)

    def test_normalize_candidate_sort_preserves_added_columns(self):
        self.assertEqual(_normalize_candidate_sort("source_ip", "asc"), ("source_ip", "ASC"))
        self.assertEqual(_normalize_candidate_sort("analysis_status", "desc"), ("analysis_status", "DESC"))
        self.assertEqual(_normalize_candidate_sort("is_focused", "asc"), ("is_focused", "ASC"))


if __name__ == "__main__":
    unittest.main()
