import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.api.events import extract_iocs_from_text


class TestEventExtraction(unittest.TestCase):
    def test_device_marker_collects_hashes_until_md5_or_sha1_line(self):
        text = """事件说明
设备ID:
abcdef1234567890
1234567890abcdef feedfacecafebeef

设备ID：cafebabecafebabe
deadbeefdeadbeef
MD5: 9999aaaaaaaa8888
ffffffffffffffff
SHA1: 1234567890abcdef1234567890abcdef12345678
"""
        result = extract_iocs_from_text(text)
        self.assertEqual(
            result["devices"],
            [
                "ABCDEF1234567890",
                "1234567890ABCDEF",
                "FEEDFACECAFEBEEF",
                "CAFEBABECAFEBABE",
                "DEADBEEFDEADBEEF",
            ],
        )

    def test_device_marker_accepts_same_line_hashes_and_no_context_lines(self):
        text = """device id: aaaabbbbccccdddd eeeeffff00001111
2222333344445555
6666777788889999
sha1 list below
ffffffffeeeeeeeeddddddddccccccccbbbbbbbbaaaaaaaa
"""
        result = extract_iocs_from_text(text)
        self.assertEqual(
            result["devices"],
            [
                "AAAABBBBCCCCDDDD",
                "EEEEFFFF00001111",
                "2222333344445555",
                "6666777788889999",
            ],
        )


if __name__ == "__main__":
    unittest.main()
