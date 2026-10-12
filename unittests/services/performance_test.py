"""Tests for the performance service and command (TP-20261004-002)."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from rsassistant.bot.cogs import holdings, performance as perf_cog
from rsassistant.persistence import performance as repo
from rsassistant.persistence.accounts import get_or_create_account_id, resolve_broker_account_ids
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

    def test_window_boundaries_and_math(self):
        self.snap("r1", "2026-01-02 10:00:00", {self.a: 800, self.b: 200})
        self.snap("r2", "2026-09-10 10:00:00", {self.a: 900, self.b: 100})
        self.snap("r3", "2026-10-03 10:00:00", {self.a: 950, self.b: 100})
        self.snap("r4", "2026-10-09 10:00:00", {self.a: 1000, self.b: 200})
        self.snap("r5", "2026-10-10 09:00:00", {self.a: 1100, self.b: 150})
        s = self.summary("1d")
        self.assertEqual(s["change"]["start_value"], 1200)  # Oct 9
        self.assertEqual(s["change"]["change"], 50)
        self.assertEqual(self.summary("7d")["change"]["start_value"], 1050)  # Oct 3
        self.assertEqual(self.summary("30d")["change"]["start_value"], 1000)  # Sep 10
        self.assertAlmostEqual(self.summary("30d")["change"]["pct"], 25.0)
        # 90d target Jul 12 -> Jan 2 snapshot is the nearest at-or-before
        self.assertEqual(self.summary("90d")["change"]["start_value"], 1000)
        self.assertEqual(self.summary("all")["change"]["start_value"], 1000)
        # ytd: nothing at/before Jan 1, so earliest after it
        self.assertEqual(self.summary("ytd")["change"]["start_value"], 1000)

    def test_negative_change_and_zero_start(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 0})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 50})
        s = self.summary("30d")
        self.assertEqual(s["change"]["change"], 50)
        self.assertIsNone(s["change"]["pct"])
        self.snap("r3", "2026-10-10 10:00:00", {self.a: 20})
        self.assertEqual(self.summary("1d")["change"]["change"], 20)

    def test_insufficient_history_still_shows_current(self):
        self.snap("r1", "2026-10-09 10:00:00", {self.a: 500})
        s = self.summary("90d")
        self.assertTrue(s["has_data"])
        self.assertEqual(s["current_value"], 500)
        self.assertIsNone(s["change"]["change"])
        text = perf_cog.format_summary(s)
        self.assertIn("Not enough history", text)
        self.assertIn("N/A", text)

    def test_new_account_is_not_fake_growth(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 1000})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 1100, self.b: 5000})
        s = self.summary("30d")
        self.assertEqual(s["current_value"], 6100)
        self.assertEqual(s["change"]["change"], 100)
        self.assertEqual(s["change"]["added_accounts"], [self.b])
        self.assertIn("common accounts", perf_cog.format_summary(s))

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
        self.assertIn("mixed", perf_cog.format_summary(s))

    def test_account_and_broker_filters(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 1000, self.b: 100})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 1200, self.b: 90})
        self.assertEqual(self.summary("30d", [self.a])["change"]["change"], 200)
        self.assertEqual(self.summary("30d", [self.b])["current_value"], 90)
        ids = resolve_broker_account_ids("fidelity", database=self.db)
        self.assertEqual(ids, [self.a])

    def test_series_and_chart(self):
        self.snap("r1", "2026-09-01 10:00:00", {self.a: 1000})
        self.snap("r2", "2026-10-10 09:00:00", {self.a: 1200})
        points = svc.get_performance_series("30d", None, AS_OF, database=self.db)
        self.assertEqual([p["effective_value"] for p in points], [1000, 1200])
        png = perf_cog.render_chart(points, "t")
        self.assertTrue(png is None or png.startswith(b"\x89PNG"))

    def test_downsample_keeps_source_rows(self):
        for day in range(1, 29):
            self.snap(f"a{day}", f"2026-01-{day:02d} 09:00:00", {self.a: day})
            self.snap(f"b{day}", f"2026-01-{day:02d} 15:00:00", {self.a: day + 0.5})
        self.snap("z", "2026-10-10 09:00:00", {self.a: 99})
        points = svc.get_performance_series("all", None, AS_OF, database=self.db)
        self.assertLess(len(points), 57)  # daily buckets for a ~9 month span
        self.assertEqual(len(repo.list_account_value_snapshots(database=self.db)), 57)

    def test_bad_window(self):
        with self.assertRaises(ValueError):
            svc.normalize_window("2w")

    def test_history_command_stays_quantity_focused(self):
        cmd = holdings.HoldingsCog.holdings_history
        self.assertIn("quantity", cmd.help)
        self.assertIn("performance", cmd.help)


if __name__ == "__main__":
    unittest.main()
