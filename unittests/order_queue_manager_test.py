"""Tests for transactional SQLite order queue persistence."""

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from utils import order_queue_manager as queue


class OrderQueueManagerTest(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "orders.db"
        self.legacy = Path(self.temp_dir.name) / "order_queue.json"
        self.patchers = [
            patch.object(queue, "DATABASE_PATH", self.database),
            patch.object(queue, "QUEUE_FILE", self.legacy),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(lambda: [patcher.stop() for patcher in self.patchers])

    def test_add_list_update_and_remove(self):
        item = {
            "action": "buy",
            "ticker": "TEST",
            "quantity": 1,
            "broker": "all",
            "time": "2025-01-01 09:30:00",
        }
        queue.add_to_order_queue("uuid-1", item)
        self.assertEqual(queue.get_order_queue(), {"uuid-1": item})

        self.assertTrue(queue.update_order_time("uuid-1", "2025-01-02 09:30:00"))
        self.assertEqual(
            queue.get_order_queue()["uuid-1"]["time"], "2025-01-02 09:30:00"
        )
        self.assertTrue(queue.remove_order("uuid-1"))
        self.assertFalse(queue.remove_order("uuid-1"))

    def test_imports_legacy_json_once(self):
        self.legacy.write_text(
            '{"old-order": {"action": "sell", "ticker": "XYZ", "quantity": 1, '
            '"broker": "all", "time": "2025-01-01 09:30:00"}}',
            encoding="utf-8",
        )
        self.assertIn("old-order", queue.get_order_queue())
        self.assertFalse(self.legacy.exists())
        self.assertTrue(self.legacy.with_suffix(".json.migrated").exists())

    def test_migrates_existing_sql_json_payload_table(self):
        with sqlite3.connect(self.database) as conn:
            conn.executescript(
                """
                CREATE TABLE order_queue (
                    order_id TEXT PRIMARY KEY,
                    order_data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                PRAGMA user_version = 4;
                """
            )
            conn.execute(
                "INSERT INTO order_queue(order_id, order_data) VALUES (?, ?)",
                (
                    "existing-order",
                    json.dumps(
                        {
                            "action": "buy",
                            "ticker": "ABC",
                            "quantity": 3,
                            "broker": "all",
                            "time": "2026-10-03 09:30:00",
                            "status": "PENDING",
                        }
                    ),
                ),
            )

        self.assertEqual(
            queue.get_order_queue()["existing-order"]["status"], "PENDING"
        )
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(
                conn.execute("PRAGMA user_version").fetchone()[0], 8
            )
            self.assertIsNone(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='order_queue'"
                ).fetchone()
            )
            self.assertEqual(
                conn.execute(
                    "SELECT scheduled_at FROM scheduled_orders WHERE order_id=?",
                    ("existing-order",),
                ).fetchone()[0],
                "2026-10-03 09:30:00",
            )

    def test_malformed_legacy_json_is_left_in_place(self):
        self.legacy.write_text("{bad json", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            queue.get_order_queue()

        self.assertTrue(self.legacy.exists())
        self.assertFalse(self.legacy.with_suffix(".json.migrated").exists())
