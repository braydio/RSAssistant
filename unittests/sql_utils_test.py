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
                FROM Accounts
                WHERE broker = ? AND broker_number = ? AND account_number = ?
                """,
                ("BrokerA", "1", "1234"),
            )
            account_nickname = cursor.fetchone()[0]

        self.assertEqual(account_nickname, "Beta")

    def test_account_identity_is_unique_and_clear_removes_mapping_state(self):
        first_id = sql_utils.get_or_create_account_id("BrokerA", "1", "1234")
        second_id = sql_utils.get_or_create_account_id("BrokerA", "1", "1234")
        self.assertEqual(first_id, second_id)

        sql_utils.upsert_account_mapping("BrokerA", "1", "1234", "Primary")
        self.assertTrue(sql_utils.has_account_mappings())
        self.assertEqual(sql_utils.clear_account_nicknames(), 1)
        self.assertFalse(sql_utils.has_account_mappings())
        self.assertEqual(sql_utils.fetch_account_mappings(), {})

    def test_resolve_account_id_always_returns_integer_id(self):
        account_id = sql_utils.get_or_create_account_id(
            "BrokerA", "1", "1234", "Primary"
        )
        self.assertEqual(sql_utils.resolve_account_id(str(account_id)), account_id)
        self.assertEqual(sql_utils.resolve_account_id("primary"), account_id)
        self.assertIsNone(sql_utils.resolve_account_id("missing"))

    def test_connections_enforce_foreign_keys_and_busy_timeout(self):
        with sql_utils.get_db_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    """INSERT INTO HoldingsLive
                       (account_id, ticker, quantity, average_price)
                       VALUES (999999, 'NONE', 1, 1)"""
                )

    def test_runtime_database_remains_available_when_legacy_sql_toggle_is_disabled(self):
        sql_utils.SQL_LOGGING_ENABLED = False

        sql_utils.init_db()
        account_id = sql_utils.get_or_create_account_id("BrokerA", "1", "1234")
        sql_utils.upsert_account_mapping("BrokerA", "1", "1234", "Primary")

        self.assertIsInstance(account_id, int)
        self.assertEqual(
            sql_utils.fetch_account_mappings(),
            {"BrokerA": {"1": {"1234": "Primary"}}},
        )
        with sql_utils.get_db_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 8)

    def test_historical_holdings_uses_latest_daily_observation_idempotently(self):
        account_id = sql_utils.get_or_create_account_id("BrokerA", "1", "1234")
        with sql_utils.get_db_connection() as conn:
            conn.executemany(
                """INSERT INTO HoldingsLive
                   (account_id, ticker, quantity, average_price, timestamp)
                   VALUES (?, 'TEST', ?, ?, ?)""",
                [
                    (account_id, 10, 2.0, "2026-08-15 10:00:00"),
                    (account_id, 20, 3.0, "2026-08-15 16:00:00"),
                ],
            )

        sql_utils.update_historical_holdings("2026-08-15")
        sql_utils.update_historical_holdings("2026-08-15")

        with sql_utils.get_db_connection() as conn:
            rows = conn.execute(
                """SELECT quantity, average_price FROM HistoricalHoldings
                   WHERE account_id=? AND ticker='TEST' AND date='2026-08-15'""",
                (account_id,),
            ).fetchall()
        self.assertEqual(rows, [(20.0, 3.0)])

    def test_init_db_sets_schema_version_and_required_indexes(self):
        with sql_utils.get_db_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 8)
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
        self.assertIn("uq_accounts_identity", indexes)
        self.assertIn("uq_historical_holdings_daily", indexes)
        self.assertIn("idx_order_history_ticker_date", indexes)

    def test_migration_collapses_legacy_account_and_history_duplicates(self):
        legacy_path = Path(self.temp_dir.name) / "legacy-schema.db"
        with sqlite3.connect(legacy_path) as conn:
            conn.executescript(
                """
                CREATE TABLE Accounts (
                    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    broker TEXT NOT NULL,
                    account_number TEXT NOT NULL,
                    account_nickname TEXT,
                    broker_number TEXT
                );
                CREATE TABLE HistoricalHoldings (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    average_price REAL NOT NULL
                );
                INSERT INTO Accounts
                    (broker, account_number, account_nickname, broker_number)
                VALUES ('BrokerA', '1234', NULL, '1'),
                       ('BrokerA', '1234', 'Primary', '1');
                INSERT INTO HistoricalHoldings
                    (account_id, ticker, date, quantity, average_price)
                VALUES (1, 'TEST', '2026-08-15', 10, 2),
                       (2, 'TEST', '2026-08-15', 20, 3);
                """
            )

        current_path = sql_utils.SQL_DATABASE
        try:
            sql_utils.SQL_DATABASE = legacy_path
            sql_utils.init_db()
            with sql_utils.get_db_connection() as conn:
                accounts = conn.execute(
                    "SELECT account_id, account_nickname FROM Accounts"
                ).fetchall()
                history = conn.execute(
                    """SELECT account_id, quantity FROM HistoricalHoldings
                       WHERE ticker='TEST' AND date='2026-08-15'"""
                ).fetchall()
            self.assertEqual(accounts, [(1, "Primary")])
            self.assertEqual(history, [(1, 20.0)])
        finally:
            sql_utils.SQL_DATABASE = current_path

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

    def test_reverse_split_log_helpers(self):
        sql_utils.insert_reverse_split_log_entry(
            ticker="TST",
            split_ratio="1-20",
            split_date="04/22",
            source="unit-test",
            ingestion_timestamp="2025-01-01 08:30:00",
        )
        sql_utils.insert_reverse_split_log_entry(
            ticker="TST",
            split_ratio="1-25",
            split_date="05/22",
            source="unit-test",
            ingestion_timestamp="2025-01-02 08:30:00",
        )

        history = sql_utils.fetch_reverse_split_history("tst")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["split_ratio"], "1-25")
        self.assertEqual(history[1]["split_ratio"], "1-20")
        self.assertEqual(history[0]["ticker"], "TST")

    def test_reverse_split_account_entry_helpers(self):
        account_id = sql_utils.get_or_create_account_id("BrokerA", "1", "1001")
        sql_utils.insert_reverse_split_account_entry(
            account_id=account_id,
            ticker="TST",
            entry_type="cost",
            price=2.5,
            source="unit-test",
            timestamp="2025-01-01 09:15:00",
        )
        sql_utils.insert_reverse_split_account_entry(
            account_id=account_id,
            ticker="TST",
            entry_type="proceeds",
            price=3.0,
            source="unit-test",
            timestamp="2025-01-01 09:16:00",
        )

        entries = sql_utils.fetch_reverse_split_account_entries(account_id, "tst")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["entry_type"], "proceeds")
        self.assertEqual(entries[1]["entry_type"], "cost")
        self.assertEqual(entries[0]["ticker"], "TST")

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
