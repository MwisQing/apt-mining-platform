import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.api.alerts import _build_filter_options


class TestBuildFilterOptions(unittest.TestCase):
    def test_empty_items(self):
        result = _build_filter_options([])
        self.assertEqual(result["device_tags"], [])
        self.assertEqual(result["threat_type"], [])
        self.assertEqual(result["std_apt_org"], [])
        self.assertEqual(result["priority"], ["高优先", "中优先", "观察"])
        self.assertEqual(result["port"], [])
        self.assertEqual(result["badges"], [])
        self.assertIsNone(result["ioc_note"])

    def test_single_item(self):
        items = [
            {
                "threat_type": "apt",
                "std_apt_org": "oceanlotus",
                "port": "443",
                "device_tags": [{"id": 1, "name": "重点设备", "color": "#F56C6C"}],
                "badges": [{"name": "apt_dict", "label": "APT词典", "color": "red"}],
                "candidate_priority": {"id": "p1", "label": "高优先", "rank": 1},
            }
        ]
        result = _build_filter_options(items)
        self.assertEqual(result["threat_type"], ["apt"])
        self.assertEqual(result["std_apt_org"], ["oceanlotus"])
        self.assertEqual(result["port"], ["443"])
        self.assertEqual(result["device_tags"], ["重点设备"])
        self.assertEqual(result["badges"], ["APT词典"])

    def test_deduplication(self):
        items = [
            {"threat_type": "apt", "std_apt_org": "oceanlotus", "port": "443", "device_tags": [], "badges": []},
            {"threat_type": "apt", "std_apt_org": "apt29", "port": "443", "device_tags": [], "badges": []},
            {"threat_type": "远控", "std_apt_org": "oceanlotus", "port": "8080", "device_tags": [], "badges": []},
        ]
        result = _build_filter_options(items)
        self.assertEqual(result["threat_type"], ["apt", "远控"])
        self.assertEqual(result["std_apt_org"], ["apt29", "oceanlotus"])
        self.assertEqual(result["port"], ["443", "8080"])


if __name__ == "__main__":
    unittest.main()
