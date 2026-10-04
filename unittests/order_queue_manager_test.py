"""Tests for transactional SQLite order queue persistence."""

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
