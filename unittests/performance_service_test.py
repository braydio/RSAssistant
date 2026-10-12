"""Tests for the performance service (TP-20261004-002)."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from rsassistant.persistence import performance as repo
from rsassistant.persistence.accounts import fetch_account_identities, get_or_create_account_id
from rsassistant.persistence.db import connect_runtime_db, initialize_runtime_db
from rsassistant.services import performance as svc

AS_OF = datetime(2026, 10, 10, 12, 0, 0)


class PerformanceServiceTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "p.db"
        initialize_runtime_db(self.db)
        self.a = get_or_create_account_id("Fidelity", "1", "A", "Acct A", database=self.db)
        self.b = get_or_create_account_id("Robinhood", "1", "B", "Acct B", database=self.db)

    def snap(self, refresh, when, values, basis="reported_total"):
        with connect_runtime_db(self.db) as conn:
            conn.execute("BEGIN IMMEDIATE") if not conn.in_transaction else None
            accounts = [
                {"account_id": i, "positions_value": v,
                 "reported_account_total": v if basis == "reported_total" else None,
                 "valuation_basis": basis}
                for i, v in values.items()
            ]
            repo.record_account_value_snapshots(
                conn, refresh, source="t", observed_at=when, accounts=accounts)
            conn.commit()

    def summary(self, window, ids=None):
        return svc.get_performance_summary(window, ids, AS_OF, database=self.db)

    def seed_history(self):
        self.snap("r1", "2026-01-02 09:00:00", {self.a: 800, self.b: 200})
        self.snap("r2", "2026-09-10 09:00:00", {self.a: 900, self.b: 100})
        self.snap("r3", "2026-10-03 09:00:00", {self.a: 950, self.b: 100})
        self.snap("r4", "2026-10-09 09:00:00", {self.a: 1000, self.b: 200})
        self.snap("r5", "2026-10-10 09:00:00", {self.a: 1100, self.b: 150})

    def test_window_boundaries_and_math(self):
        self.seed_history()
        expected = {"1d": 1200, "7d": 1050, "30d": 1000, "90d": 1000,
                    "ytd": 1000, "all": 1000}
        for window, start in expected.items():
            self.assertEqual(self.summary(window)["change"]["start_value"], start, window)
        s = self.summary("30d")
        self.assertEqual(s["change"]["change"], 250)
        self.assertAlmostEqual(s["change"]["pct"], 25.0)
        self.assertEqual(self.summary("1d")["change"]["change"], 50)
        # no observation at/before 2025-10-10 -> unavailable, never a partial period
        self.assertIsNone(self.summary("1y")["change"]["change"])

    def test_ytd_prefers_observation_before_jan_1(self):
        self.snap("p", "2025-12-30 09:00:00", {self.a: 700})
        self.snap("q", "2026-02-01 09:00:00", {self.a: 800})
        self.snap("r", "2026-10-10 09:00:00", {self.a: 900})
        self.assertEqual(self.summary("ytd")["change"]["start_value"], 700)

    def test_negative_change(self):
        self.snap("r1", "2026-09-01 09:00:00", {self.a: 1000})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 900})
        self.assertEqual(self.summary("30d")["change"]["change"], -100)
        self.assertAlmostEqual(self.summary("30d")["change"]["pct"], -10.0)

    def test_historical_rows_group_by_date_across_accounts(self):
        with connect_runtime_db(self.db) as conn:
            conn.execute(
                "INSERT INTO HistoricalHoldings(account_id,ticker,quantity,average_price,date)"
                " VALUES (?,?,?,?,?)", (self.a, "AAA", 1, 100.0, "2026-09-01"))
            conn.execute(
                "INSERT INTO HistoricalHoldings(account_id,ticker,quantity,average_price,date)"
                " VALUES (?,?,?,?,?)", (self.b, "BBB", 1, 50.0, "2026-09-01"))
            conn.commit()
        repo.backfill_historical_account_values(database=self.db)
        self.snap("live", "2026-10-10 09:00:00", {self.a: 130, self.b: 70})
        s = self.summary("30d")
        self.assertEqual(s["change"]["start_value"], 150)  # one point, both accounts
        self.assertEqual(s["change"]["change"], 50)
        self.assertTrue(s["mixed_basis"])

    def test_zero_start(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 0})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 50})
        s = self.summary("30d")
        self.assertEqual(s["change"]["change"], 50)
        self.assertIsNone(s["change"]["pct"])

    def test_insufficient_history_still_shows_current(self):
        self.snap("r1", "2026-10-09 10:00:00", {self.a: 500})
        s = self.summary("90d")
        self.assertTrue(s["has_data"])
        self.assertEqual(s["current_value"], 500)
        self.assertIsNone(s["change"]["change"])

    def test_new_account_is_not_fake_growth(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 1000})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 1100, self.b: 5000})
        s = self.summary("30d")
        self.assertEqual(s["current_value"], 6100)
        self.assertEqual(s["change"]["change"], 100)
        self.assertEqual(s["change"]["added_accounts"], [self.b])

    def test_removed_account(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 1000, self.b: 500})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 900})
        s = self.summary("30d")
        self.assertEqual(s["change"]["change"], -100)
        self.assertEqual(s["change"]["removed_accounts"], [self.b])

    def test_mixed_basis_disclosed(self):
        self.snap("historical:2026-09-01:1", "2026-09-01 00:00:00", {self.a: 900},
                  basis="historical_positions_sum")
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 1000})
        s = self.summary("30d")
        self.assertTrue(s["mixed_basis"])

    def test_account_and_broker_filters(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 1000, self.b: 100})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 1200, self.b: 90})
        self.assertEqual(self.summary("30d", [self.a])["change"]["change"], 200)
        self.assertEqual(self.summary("30d", [self.b])["current_value"], 90)
        self.assertEqual(svc.resolve_scope("fidelity", database=self.db)[0], [self.a])
        self.assertEqual(svc.resolve_scope("acct b", database=self.db)[0], [self.b])
        self.assertEqual(svc.resolve_scope(str(self.a), database=self.db)[0], [self.a])
        self.assertEqual(svc.resolve_scope(None, database=self.db)[0], None)
        with self.assertRaises(svc.ScopeError):
            svc.resolve_scope("nope", database=self.db)
        self.assertEqual(len(fetch_account_identities(database=self.db)), 2)

    def test_series(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 1000})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 1200})
        points = svc.get_performance_series("30d", None, AS_OF, database=self.db)
        self.assertEqual([p["effective_value"] for p in points], [1000, 1200])

    def test_downsample_is_display_only(self):
        for day in range(1, 29):
            for hour in range(0, 24, 6):
                self.snap(f"a{day}{hour}", f"2026-02-{day:02d} {hour:02d}:00:00", {self.a: day})
        points = svc.get_performance_series("all", None, AS_OF, database=self.db)
        self.assertEqual(len(points), 112)  # <=120 observations -> all kept
        for day in range(1, 29):  # push past 120 observations
            self.snap(f"b{day}", f"2026-03-{day:02d} 09:00:00", {self.a: day})
        points = svc.get_performance_series("all", None, AS_OF, database=self.db)
        self.assertEqual(len(points), 56)  # 140 observations -> one per day
        self.assertEqual(len(repo.list_account_value_snapshots(database=self.db)), 140)

    def test_bad_window(self):
        with self.assertRaises(ValueError):
            svc.normalize_window("2w")



if __name__ == "__main__":
    unittest.main()
