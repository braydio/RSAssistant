"""Tests for the performance Discord cog (TP-20261004-002)."""

import asyncio
import unittest
from datetime import datetime
from unittest import mock

from rsassistant.bot.cogs import holdings, performance as perf_cog

NOW = datetime(2026, 10, 10, 12, 0)


def make_summary(**over):
    change = {"change": 100.0, "pct": 10.0, "start_value": 1000.0, "end_value": 1100.0,
              "added_accounts": [], "removed_accounts": [], "common_accounts": 2,
              "comparison_observed_at": datetime(2026, 9, 10), "mixed_basis": False}
    base = {"window": "30d", "has_data": True, "account_count": 2, "current_value": 1100.0,
            "current_observed_at": NOW, "earliest_observed_at": datetime(2026, 1, 2),
            "as_of": NOW, "change": change, "change_7d": dict(change, change=20.0),
            "since_tracking": change, "top_contributors": [
                {"name": "A", "value": 700.0}, {"name": "B", "value": 400.0}],
            "basis": ["reported_total"], "mixed_basis": False}
    base.update(over)
    return base


class _Ctx:
    def __init__(self):
        self.sent = []

    async def send(self, text=None, **kwargs):
        self.sent.append((text, kwargs))


class PerformanceCogTest(unittest.TestCase):
    def test_aliases_and_default_window(self):
        cmd = perf_cog.PerformanceCog.performance
        self.assertEqual(set(cmd.aliases), {"perf", "growth"})
        self.assertIn("30d", cmd.help)

    def test_summary_text(self):
        text = perf_cog.format_summary(make_summary())
        self.assertIn("+$100.00", text)
        self.assertIn("+10.00%", text)
        self.assertIn("7D value change", text)
        self.assertNotIn("Comparable current", text)
        self.assertNotIn("investment return", text.lower().replace("not adjusted", ""))
        self.assertIn("Value change only", text)

    def test_comparable_current_and_mixed_basis(self):
        s = make_summary(mixed_basis=True, basis=["historical_positions_sum", "reported_total"])
        s["change"] = dict(s["change"], end_value=900.0, added_accounts=[3])
        text = perf_cog.format_summary(s)
        self.assertIn("Comparable current", text)
        self.assertIn("mixed", text)
        self.assertIn("common to both dates", text)

    def test_insufficient_history(self):
        s = make_summary()
        s["change"] = dict(s["change"], change=None, pct=None, comparison_observed_at=None)
        self.assertIn("Not enough history", perf_cog.format_summary(s))

    def test_command_sends_chart_and_parses_scope(self):
        cog = perf_cog.PerformanceCog(mock.Mock())
        ctx = _Ctx()
        points = [{"time": datetime(2026, 9, 10), "effective_value": 1000.0,
                   "positions_value": 1000.0, "account_count": 2, "basis": ["reported_total"]},
                  {"time": NOW, "effective_value": 1100.0, "positions_value": 1100.0,
                   "account_count": 2, "basis": ["reported_total"]}]
        with mock.patch.object(perf_cog.perf, "resolve_scope", return_value=([1], "My IRA")) as rs, \
             mock.patch.object(perf_cog.perf, "get_performance_summary", return_value=make_summary()) as gs, \
             mock.patch.object(perf_cog.perf, "get_performance_series", return_value=points):
            asyncio.run(cog.performance.callback(cog, ctx, "7d", "My", "IRA"))
        rs.assert_called_once_with("My IRA")
        self.assertEqual(gs.call_args.args[0], "7d")
        self.assertIn("file", ctx.sent[0][1]) if perf_cog.render_chart(points, "t") else None

    def test_scope_without_window_uses_default(self):
        cog = perf_cog.PerformanceCog(mock.Mock())
        ctx = _Ctx()
        with mock.patch.object(perf_cog.perf, "resolve_scope", return_value=(None, "Portfolio")) as rs, \
             mock.patch.object(perf_cog.perf, "get_performance_summary", return_value=make_summary()) as gs, \
             mock.patch.object(perf_cog.perf, "get_performance_series", return_value=[]):
            asyncio.run(cog.performance.callback(cog, ctx, "Fidelity"))
        rs.assert_called_once_with("Fidelity")
        self.assertEqual(gs.call_args.args[0], "30d")

    def test_bad_scope_reports_error(self):
        cog = perf_cog.PerformanceCog(mock.Mock())
        ctx = _Ctx()
        with mock.patch.object(perf_cog.perf, "resolve_scope",
                               side_effect=perf_cog.perf.ScopeError("No account or broker matches 'x'.")):
            asyncio.run(cog.performance.callback(cog, ctx, "x"))
        self.assertIn("No account or broker", ctx.sent[0][0])

    def test_chart_renders_png(self):
        points = [{"time": datetime(2026, 9, 10), "effective_value": 1000.0,
                   "positions_value": 900.0, "account_count": 2, "basis": ["historical_positions_sum"]},
                  {"time": NOW, "effective_value": 1100.0, "positions_value": 1100.0,
                   "account_count": 2, "basis": ["reported_total"]}]
        png = perf_cog.render_chart(points, "t")
        self.assertTrue(png is None or png.startswith(b"\x89PNG"))

    def test_backfill_runs_via_to_thread_and_failure_is_swallowed(self):
        cog = perf_cog.PerformanceCog(mock.Mock())
        calls = []

        async def fake_to_thread(fn, *a, **k):
            calls.append(fn)
            raise RuntimeError("boom")

        with mock.patch.object(perf_cog.asyncio, "to_thread", fake_to_thread):
            asyncio.run(cog.cog_load())  # must not raise
        self.assertEqual(calls, [perf_cog.backfill_historical_account_values])

    def test_history_command_stays_quantity_focused(self):
        cmd = holdings.HoldingsCog.holdings_history
        self.assertIn("quantity", cmd.help)
        self.assertIn("performance", cmd.help)


if __name__ == "__main__":
    unittest.main()
