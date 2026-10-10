"""Tests for atomic current holdings persistence."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence.holdings import (
    activate_staged_holdings,
    discard_staged_holdings,
    get_current_holdings,
    replace_current_holdings,
    stage_current_holdings,
)


class HoldingsRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "holdings.db"
        self.addCleanup(self.temp_dir.cleanup)

    def holding(self, ticker="AAA", **overrides):
        return {
            "broker": "BrokerA",
            "broker_number": "1",
            "account_number": "0001",
            "ticker": ticker,
            "quantity": 2,
            "price": 3.5,
            "position_value": 7,
            "account_total": 40,
            "observed_at": "2026-10-03 09:30:00",
            "source": "test",
            **overrides,
        }

    def test_snapshot_preserves_identity_totals_timestamps_and_negative_positions(self):
        count = replace_current_holdings(
            [self.holding("SHORT", quantity=-2, position_value=-7)],
            database=self.database,
        )

        rows = get_current_holdings(database=self.database)

        self.assertEqual(count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["broker"], "BrokerA")
        self.assertEqual(rows[0]["broker_number"], "1")
        self.assertEqual(rows[0]["account_number"], "0001")
        self.assertEqual(rows[0]["ticker"], "SHORT")
        self.assertEqual(rows[0]["quantity"], -2)
        self.assertEqual(rows[0]["position_value"], -7)
        self.assertEqual(rows[0]["account_total"], 40)
        self.assertEqual(rows[0]["observed_at"], "2026-10-03 09:30:00")
        self.assertEqual(rows[0]["source"], "test")

    def test_refresh_staging_is_invisible_until_atomic_activation(self):
        replace_current_holdings([self.holding("AAA")], database=self.database)
        stage_current_holdings(
            "refresh-1",
            [self.holding("BBB", quantity=-1, position_value=-3.5)],
            database=self.database,
        )

        self.assertEqual(
            [row["ticker"] for row in get_current_holdings(database=self.database)],
            ["AAA"],
        )
        self.assertTrue(activate_staged_holdings("refresh-1", database=self.database))
        self.assertEqual(
            [row["ticker"] for row in get_current_holdings(database=self.database)],
            ["BBB"],
        )
        self.assertEqual(
            get_current_holdings(database=self.database)[0]["quantity"], -1
        )

    def test_empty_snapshot_can_be_activated_and_abort_preserves_current(self):
        replace_current_holdings([self.holding("AAA")], database=self.database)
        stage_current_holdings("abort-me", [self.holding("BBB")], database=self.database)
        discard_staged_holdings("abort-me", database=self.database)
        self.assertEqual(
            [row["ticker"] for row in get_current_holdings(database=self.database)],
            ["AAA"],
        )

        stage_current_holdings("empty", [], database=self.database)
        self.assertTrue(activate_staged_holdings("empty", database=self.database))
        self.assertEqual(get_current_holdings(database=self.database), [])

    def test_failed_insert_rolls_back_without_losing_previous_snapshot(self):
        replace_current_holdings([self.holding("AAA")], database=self.database)
        with sqlite3.connect(self.database) as conn:
            conn.execute(
                """CREATE TRIGGER reject_failure_ticker
                   BEFORE INSERT ON holdings_current
                   WHEN NEW.ticker='FAIL'
                   BEGIN SELECT RAISE(ABORT, 'forced test failure'); END"""
            )

        with self.assertRaises(sqlite3.IntegrityError):
            replace_current_holdings(
                [self.holding("BBB"), self.holding("FAIL")], database=self.database
            )

        self.assertEqual(
            [row["ticker"] for row in get_current_holdings(database=self.database)],
            ["AAA"],
        )

    def test_invalid_rows_fail_before_existing_snapshot_is_replaced(self):
        replace_current_holdings([self.holding("AAA")], database=self.database)

        with self.assertRaises(ValueError):
            replace_current_holdings(
                [self.holding("BROKEN", quantity=float("nan"))],
                database=self.database,
            )

        self.assertEqual(
            [row["ticker"] for row in get_current_holdings(database=self.database)],
            ["AAA"],
        )


if __name__ == "__main__":  # pragma: no cover - convenience for direct execution
    unittest.main()
