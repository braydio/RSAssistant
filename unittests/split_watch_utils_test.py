"""Tests for SQLite-backed reverse-split monitor state."""

import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from utils import split_watch_utils as split_watch


class SplitWatchUtilsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "runtime.db"
        self.legacy = Path(self.temp_dir.name) / "split_watchlist.json"
        self.patchers = [
            patch.object(split_watch, "DATABASE_PATH", self.database),
            patch.object(split_watch, "SPLIT_WATCH_FILE", self.legacy),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(lambda: [patcher.stop() for patcher in self.patchers])

    def test_account_marks_are_idempotent_and_completed_entries_cascade_delete(self):
        split_watch.add_split_watch("abc", "2000-01-01")
        split_watch.mark_account_bought("ABC", "Broker 1")
        split_watch.mark_account_bought("ABC", "Broker 1")
        split_watch.mark_account_sold("ABC", "Broker 1")
        split_watch.update_split_status()

        self.assertEqual(
            split_watch.get_status("abc"),
            {
                "split_date": "2000-01-01",
                "status": "selling",
                "accounts_bought": ["Broker 1"],
                "accounts_sold": ["Broker 1"],
            },
        )
        self.assertEqual(split_watch.get_all_accounts(), {"Broker 1"})

        split_watch.cleanup_completed_tickers()

        self.assertIsNone(split_watch.get_status("ABC"))
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM split_monitor_accounts").fetchone()[0],
                0,
            )

    def test_expired_cleanup_removes_only_past_iso_dates(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        split_watch.add_split_watch("OLD", yesterday)
        split_watch.add_split_watch("FUTURE", tomorrow)
        split_watch.add_split_watch("INVALID", "not-a-date")

        self.assertEqual(split_watch.cleanup_expired_tickers(), ["OLD"])
        self.assertEqual(split_watch.get_watchlist(), ["FUTURE", "INVALID"])

    def test_imports_legacy_json_once_and_preserves_dictionary_shape(self):
        self.legacy.write_text(
            json.dumps(
                {
                    "watchlist": {
                        "xyz": {
                            "split_date": "2026-12-01",
                            "status": "selling",
                            "accounts_bought": ["A", "B"],
                            "accounts_sold": ["B"],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        state = split_watch.load_data()

        self.assertEqual(
            state["watchlist"]["XYZ"],
            {
                "split_date": "2026-12-01",
                "status": "selling",
                "accounts_bought": ["A", "B"],
                "accounts_sold": ["B"],
            },
        )
        self.assertFalse(self.legacy.exists())
        self.assertTrue(self.legacy.with_suffix(".json.migrated").exists())
        self.assertEqual(split_watch.get_status("XYZ")["accounts_bought"], ["A", "B"])

    def test_malformed_legacy_json_remains_available_for_recovery(self):
        self.legacy.write_text("{bad json", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            split_watch.get_full_watchlist()

        self.assertTrue(self.legacy.exists())
        self.assertFalse(self.legacy.with_suffix(".json.migrated").exists())

    def test_remove_split_watch_reports_presence_and_cascades_accounts(self):
        split_watch.add_split_watch("abc", "2026-12-01")
        split_watch.mark_account_bought("abc", "A")

        self.assertTrue(split_watch.remove_split_watch("ABC"))
        self.assertFalse(split_watch.remove_split_watch("ABC"))
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM split_monitor_accounts").fetchone()[0],
                0,
            )


if __name__ == "__main__":  # pragma: no cover - convenience for direct execution
    unittest.main()
