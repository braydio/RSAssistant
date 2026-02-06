"""Unit tests for SQL utility helpers."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils import sql_utils


class SqlUtilsAccountMappingTest(unittest.TestCase):
    """Validate SQL account mapping synchronization."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.legacy_dir = Path(self.temp_dir.name) / "legacy"
        self.legacy_dir.mkdir(parents=True, exist_ok=True)

        self.original_db = sql_utils.SQL_DATABASE
        self.original_enabled = sql_utils.SQL_LOGGING_ENABLED
        self.original_account_mapping = sql_utils.ACCOUNT_MAPPING
        self.original_watch_file = sql_utils.WATCH_FILE
        self.original_sell_file = sql_utils.SELL_FILE

        sql_utils.SQL_DATABASE = self.db_path
        sql_utils.SQL_LOGGING_ENABLED = True
        sql_utils.ACCOUNT_MAPPING = self.legacy_dir / "account_mapping.json"
        sql_utils.WATCH_FILE = self.legacy_dir / "watch_list.json"
        sql_utils.SELL_FILE = self.legacy_dir / "sell_list.json"
        sql_utils.init_db()

    def tearDown(self):
        sql_utils.SQL_DATABASE = self.original_db
        sql_utils.SQL_LOGGING_ENABLED = self.original_enabled
        sql_utils.ACCOUNT_MAPPING = self.original_account_mapping
        sql_utils.WATCH_FILE = self.original_watch_file
        sql_utils.SELL_FILE = self.original_sell_file
        self.temp_dir.cleanup()

    def test_sync_account_mappings_inserts_and_updates(self):
        mappings = {"BrokerA": {"1": {"1234": "Alpha"}}}
        results = sql_utils.sync_account_mappings(mappings)
        self.assertEqual(results["added"], 1)
        self.assertEqual(results["updated"], 0)

        updated_results = sql_utils.sync_account_mappings(
            {"BrokerA": {"1": {"1234": "Beta"}}}
        )
        self.assertEqual(updated_results["added"], 0)
        self.assertEqual(updated_results["updated"], 1)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT account_nickname
                FROM account_mappings
                WHERE broker = ? AND broker_number = ? AND account_number = ?
                """,
                ("BrokerA", "1", "1234"),
            )
            nickname = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT account_nickname
                FROM Accounts
                WHERE broker = ? AND broker_number = ? AND account_number = ?
                """,
                ("BrokerA", "1", "1234"),
            )
            account_nickname = cursor.fetchone()[0]

        self.assertEqual(nickname, "Beta")
        self.assertEqual(account_nickname, "Beta")

    def test_watchlist_and_sell_list_helpers(self):
        sql_utils.upsert_watchlist_entry("TEST", "01/02", "1-10", {"source": "unit"})
        watchlist = sql_utils.fetch_watchlist_entries()
        self.assertIn("TEST", watchlist)
        self.assertEqual(watchlist["TEST"]["split_date"], "01/02")
        self.assertEqual(watchlist["TEST"]["split_ratio"], "1-10")
        self.assertEqual(sql_utils.fetch_watchlist_entry("test")["split_ratio"], "1-10")

        sql_utils.upsert_sell_list_entry(
            "TEST", metadata={"broker": "all", "quantity": 0}
        )
        sell_list = sql_utils.fetch_sell_list_entries()
        self.assertIn("TEST", sell_list)
        self.assertEqual(sell_list["TEST"]["broker"], "all")
        self.assertEqual(sql_utils.fetch_sell_list_entry("test")["quantity"], 0)

    def test_replace_helpers_overwrite_existing_rows(self):
        sql_utils.upsert_watchlist_entry("OLD", "01/01", "1-5")
        written = sql_utils.replace_watchlist_entries(
            {"NEW": {"split_date": "02/02", "split_ratio": "1-10", "note": "x"}}
        )
        self.assertEqual(written, 1)
        self.assertEqual(set(sql_utils.fetch_watchlist_entries().keys()), {"NEW"})

        sql_utils.upsert_sell_list_entry("OLD", metadata={"broker": "all"})
        written = sql_utils.replace_sell_list_entries(
            {"NEW": {"broker": "all", "quantity": 1}}
        )
        self.assertEqual(written, 1)
        self.assertEqual(set(sql_utils.fetch_sell_list_entries().keys()), {"NEW"})

    def test_migrate_legacy_json_data_imports_and_archives(self):
        sql_utils.ACCOUNT_MAPPING.write_text(
            json.dumps({"BrokerA": {"1": {"1001": "Primary"}}}), encoding="utf-8"
        )
        sql_utils.WATCH_FILE.write_text(
            json.dumps({"ABCD": {"split_date": "03/03", "split_ratio": "1-20"}}),
            encoding="utf-8",
        )
        sql_utils.SELL_FILE.write_text(
            json.dumps({"WXYZ": {"broker": "all", "quantity": 0}}), encoding="utf-8"
        )

        results = sql_utils.migrate_legacy_json_data(remove_legacy_files=True)

        self.assertEqual(results["account_mappings"], 1)
        self.assertEqual(results["watchlist"], 1)
        self.assertEqual(results["sell_list"], 1)
        self.assertTrue(Path(f"{sql_utils.ACCOUNT_MAPPING}.migrated").exists())
        self.assertTrue(Path(f"{sql_utils.WATCH_FILE}.migrated").exists())
        self.assertTrue(Path(f"{sql_utils.SELL_FILE}.migrated").exists())


if __name__ == "__main__":
    unittest.main()
