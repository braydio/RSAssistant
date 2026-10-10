"""Tests for durable account/portfolio value snapshot history (TP-20261004-001)."""

import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence.db import connect_runtime_db, initialize_runtime_db
from rsassistant.persistence.holdings import (
    activate_staged_holdings,
    discard_staged_holdings,
    replace_current_holdings,
    stage_current_holdings,
)
from rsassistant.persistence import performance


def holding(ticker, account_number="0001", account_total=None, position_value=100.0,
            quantity=1, price=None, observed_at="2026-10-10 09:30:00", broker_number="1"):
    return {
        "broker": "BrokerA",
        "broker_number": broker_number,
        "account_number": account_number,
        "ticker": ticker,
        "quantity": quantity,
        "price": price if price is not None else position_value,
        "position_value": position_value,
        "account_total": account_total,
        "observed_at": observed_at,
        "source": "test",
    }


class PerformanceRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_dir.name) / "performance.db"
        self.addCleanup(self.temp_dir.cleanup)

    def test_one_snapshot_per_account_on_replace(self):
        replace_current_holdings(
            [
                holding("AAA", "0001", account_total=1000, position_value=700),
                holding("BBB", "0001", account_total=1000, position_value=300),
                holding("CCC", "0002", account_total=None, position_value=50),
            ],
            database=self.database,
        )

        snapshots = performance.latest_account_values(database=self.database)
        self.assertEqual(len(snapshots), 2)
        by_total = {row["effective_value"] for row in snapshots}
        self.assertIn(1000.0, by_total)
        self.assertIn(50.0, by_total)

    def test_repeated_account_total_rows_are_not_summed(self):
        replace_current_holdings(
            [
                holding("AAA", "0001", account_total=1000, position_value=700),
                holding("BBB", "0001", account_total=1000, position_value=300),
            ],
            database=self.database,
        )

        snapshots = performance.latest_account_values(database=self.database)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["reported_account_total"], 1000.0)
        self.assertEqual(snapshots[0]["effective_value"], 1000.0)
        self.assertEqual(snapshots[0]["valuation_basis"], "reported_total")

    def test_positions_sum_fallback_when_no_reported_total(self):
        replace_current_holdings(
            [holding("AAA", "0001", account_total=None, position_value=42.5)],
            database=self.database,
        )

        snapshots = performance.latest_account_values(database=self.database)
        self.assertEqual(snapshots[0]["effective_value"], 42.5)
        self.assertEqual(snapshots[0]["valuation_basis"], "positions_sum")

    def test_conflicting_account_totals_fall_back_without_averaging(self):
        replace_current_holdings(
            [
                holding("AAA", "0001", account_total=1000, position_value=700),
                holding("BBB", "0001", account_total=900, position_value=300),
            ],
            database=self.database,
        )

        snapshots = performance.latest_account_values(database=self.database)
        self.assertEqual(len(snapshots), 1)
        self.assertIsNone(snapshots[0]["reported_account_total"])
        self.assertEqual(snapshots[0]["effective_value"], 1000.0)
        self.assertEqual(snapshots[0]["valuation_basis"], "positions_sum")

    def test_negative_positions_included_in_positions_value(self):
        replace_current_holdings(
            [
                holding("AAA", "0001", account_total=None, position_value=100),
                holding("SHORT", "0001", account_total=None, position_value=-30,
                        quantity=-2),
            ],
            database=self.database,
        )

        snapshots = performance.latest_account_values(database=self.database)
        self.assertEqual(snapshots[0]["positions_value"], 70.0)

    def test_aborted_refresh_creates_no_snapshot(self):
        stage_current_holdings(
            "r1", [holding("AAA", account_total=500, position_value=500)],
            database=self.database,
        )
        discard_staged_holdings("r1", database=self.database)

        self.assertEqual(
            performance.list_account_value_snapshots(database=self.database), []
        )

    def test_activation_commits_exactly_one_snapshot_per_affected_account(self):
        stage_current_holdings(
            "r1",
            [
                holding("AAA", "0001", account_total=500, position_value=500),
                holding("ZZZ", "0002", account_total=None, position_value=20),
            ],
            database=self.database,
        )
        activated = activate_staged_holdings("r1", database=self.database)

        self.assertTrue(activated)
        snapshots = performance.list_account_value_snapshots(database=self.database)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual({row["refresh_id"] for row in snapshots}, {"r1"})

    def test_same_refresh_id_is_idempotent(self):
        stage_current_holdings(
            "r1", [holding("AAA", account_total=500, position_value=500)],
            database=self.database,
        )
        activate_staged_holdings("r1", database=self.database)

        with connect_runtime_db(self.database) as conn:
            performance.record_account_value_snapshots(
                conn, "r1", source="manual-retry"
            )

        self.assertEqual(
            len(performance.list_account_value_snapshots(database=self.database)), 1
        )

    def test_separate_refreshes_accumulate_history(self):
        stage_current_holdings(
            "r1", [holding("AAA", account_total=500, position_value=500)],
            database=self.database,
        )
        activate_staged_holdings("r1", database=self.database)
        stage_current_holdings(
            "r2", [holding("AAA", account_total=600, position_value=600)],
            database=self.database,
        )
        activate_staged_holdings("r2", database=self.database)

        series = performance.account_value_series(1, database=self.database)
        self.assertEqual(len(series), 2)
        self.assertEqual([row["effective_value"] for row in series], [500.0, 600.0])

    def test_historical_backfill_uses_distinct_valuation_basis(self):
        initialize_runtime_db(self.database)
        with connect_runtime_db(self.database) as conn:
            conn.execute(
                "INSERT INTO Accounts(broker, broker_number, account_number) "
                "VALUES ('BrokerA', '1', '0001')"
            )
            conn.execute(
                "INSERT INTO HistoricalHoldings"
                "(account_id, ticker, date, quantity, average_price) "
                "VALUES (1, 'AAA', '2026-09-01', 10, 5.0)"
            )
            conn.execute(
                "INSERT INTO HistoricalHoldings"
                "(account_id, ticker, date, quantity, average_price) "
                "VALUES (1, 'BBB', '2026-09-01', 4, 2.5)"
            )

        inserted = performance.backfill_historical_account_values(database=self.database)

        self.assertEqual(inserted, 1)
        rows = performance.account_value_series(1, database=self.database)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["positions_value"], 60.0)
        self.assertIsNone(rows[0]["reported_account_total"])
        self.assertEqual(rows[0]["valuation_basis"], "historical_positions_sum")

    def test_repeated_backfill_has_no_duplicates(self):
        initialize_runtime_db(self.database)
        with connect_runtime_db(self.database) as conn:
            conn.execute(
                "INSERT INTO Accounts(broker, broker_number, account_number) "
                "VALUES ('BrokerA', '1', '0001')"
            )
            conn.execute(
                "INSERT INTO HistoricalHoldings"
                "(account_id, ticker, date, quantity, average_price) "
                "VALUES (1, 'AAA', '2026-09-01', 10, 5.0)"
            )

        first = performance.backfill_historical_account_values(database=self.database)
        second = performance.backfill_historical_account_values(database=self.database)

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(
            len(performance.account_value_series(1, database=self.database)), 1
        )

    def test_latest_and_series_queries_order_correctly(self):
        stage_current_holdings(
            "r1", [holding("AAA", account_total=100, position_value=100,
                            observed_at="2026-10-01 09:30:00")],
            database=self.database,
        )
        activate_staged_holdings("r1", database=self.database)
        stage_current_holdings(
            "r2", [holding("AAA", account_total=150, position_value=150,
                            observed_at="2026-10-05 09:30:00")],
            database=self.database,
        )
        activate_staged_holdings("r2", database=self.database)

        series = performance.account_value_series(1, database=self.database)
        self.assertEqual(
            [row["observed_at"] for row in series],
            ["2026-10-01 09:30:00", "2026-10-05 09:30:00"],
        )

        latest = performance.latest_account_values(database=self.database)
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["effective_value"], 150.0)

        portfolio = performance.portfolio_value_series(database=self.database)
        self.assertEqual(len(portfolio), 2)
        self.assertEqual(portfolio[-1]["total_effective_value"], 150.0)


if __name__ == "__main__":
    unittest.main()
