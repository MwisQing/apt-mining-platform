import os
import sys
import unittest

from sqlalchemy import text
from fastapi.testclient import TestClient

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.main import app
from backend.utils.db import get_session_local, init_db


class TestTracedApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.SessionLocal = get_session_local()

    def setUp(self):
        with self.SessionLocal() as db:
            db.execute(text("DELETE FROM traced_targets"))
            db.execute(text("DELETE FROM audit_log WHERE target_type = 'traced_target'"))
            db.commit()

    def test_update_traced_normalizes_empty_port_and_updates_note(self):
        create = self.client.post("/api/traced", json={
            "target": "1.1.1.1",
            "port": "",
            "note": "old note",
        })
        self.assertEqual(create.status_code, 200)
        traced_id = create.json()["ids"][0]

        update = self.client.patch(f"/api/traced/{traced_id}", json={
            "target": "1.1.1.1",
            "port": "",
            "note": "new note",
        })
        self.assertEqual(update.status_code, 200)

        listing = self.client.get("/api/traced")
        self.assertEqual(listing.status_code, 200)
        items = listing.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["target"], "1.1.1.1")
        self.assertTrue(items[0]["port"] in (None, ""))
        self.assertEqual(items[0]["note"], "new note")

    def test_update_traced_rejects_duplicate_target_and_port(self):
        first = self.client.post("/api/traced", json={"target": "a.example.com", "port": "443", "note": "one"})
        second = self.client.post("/api/traced", json={"target": "b.example.com", "port": "443", "note": "two"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        second_id = second.json()["ids"][0]

        update = self.client.patch(f"/api/traced/{second_id}", json={
            "target": "a.example.com",
            "port": "443",
            "note": "dup",
        })
        self.assertEqual(update.status_code, 409)

    def test_create_traced_accepts_batch_payload(self):
        response = self.client.post("/api/traced", json=[
            {"target": "3.3.3.3", "port": "80", "note": "first"},
            {"target": "4.4.4.4", "port": "", "note": "second"},
        ])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)

        listing = self.client.get("/api/traced")
        self.assertEqual(listing.status_code, 200)
        items = listing.json()
        self.assertEqual(len(items), 2)
        self.assertEqual({item["target"] for item in items}, {"3.3.3.3", "4.4.4.4"})


if __name__ == "__main__":
    unittest.main()
