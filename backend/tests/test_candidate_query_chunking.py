import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.api.alerts import _event_maps_for_rows


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeRow:
    def __init__(self, target, port="443"):
        self._mapping = {
            "target": target,
            "port": port,
            "device_id": "device-1",
        }


class ChunkingDb:
    def __init__(self, max_vars=900):
        self.max_vars = max_vars
        self.calls = []

    def execute(self, stmt, params):
        self.calls.append(len(params))
        if len(params) > self.max_vars:
            raise AssertionError(f"query used too many vars: {len(params)}")
        return FakeResult([])


class TestCandidateQueryChunking(unittest.TestCase):
    def test_event_maps_chunk_large_target_list(self):
        rows = [FakeRow(f"target-{i}.example.com") for i in range(1205)]
        db = ChunkingDb(max_vars=900)

        _event_maps_for_rows(db, rows)

        self.assertGreater(len(db.calls), 1)
        self.assertTrue(all(size <= 900 for size in db.calls))


if __name__ == "__main__":
    unittest.main()
