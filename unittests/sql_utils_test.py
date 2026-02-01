"""Unit tests for SQL utility helpers."""

import sqlite3
import tempfile
import unittest

from utils import sql_utils


class SqlUtilsAccountMappingTest(unittest.TestCase):
    """Validate SQL account mapping synchronization."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/test.db"
        self.original_db = sql_utils.SQL_DATABASE
        self.original_enabled = sql_utils.SQL_LOGGING_ENABLED
        sql_utils.SQL_DATABASE = self.db_path
        sql_utils.SQL_LOGGING_ENABLED = True
        sql_utils.init_db()

    def tearDown(self):
        sql_utils.SQL_DATABASE = self.original_db
        sql_utils.SQL_LOGGING_ENABLED = self.original_enabled
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
            nickname = cursor.fetchone()[0]

        self.assertEqual(nickname, "Beta")
