"""Tests for opt-in resource metrics (TP-20261010-001)."""

import asyncio
import logging
import unittest
from unittest import mock

from rsassistant.bot import tasks
from utils import config_utils, performance_metrics as pm


class PerformanceMetricsTest(unittest.TestCase):
    def setUp(self):
        pm.reset_calls()
        pm._task = None

    def test_disabled_by_default(self):
        self.assertFalse(config_utils.RESOURCE_METRICS_ENABLED)
        self.assertEqual(config_utils.RESOURCE_METRICS_INTERVAL_SECONDS, 300)

        async def run():
            return pm.start_metrics_task(False, 300)

        self.assertIsNone(asyncio.run(run()))

    def test_snapshot_format(self):
        pm.record_call("yfinance_batch", 0.5)
        snap = asyncio.run(pm.collect_snapshot())
        text = pm.format_snapshot(snap)
        for key in ("cpu_s=", "rss_kib=", "loop_drift_ms=", "tasks=", "yfinance_batch=1/0.50s"):
            self.assertIn(key, text)
        self.assertGreaterEqual(snap["loop_drift_ms"], 0)

    def test_rss_unavailable_is_not_zero(self):
        self.assertIsNone(pm.read_rss_kib("/nonexistent/status"))
        snap = {"cpu_seconds": 1.0, "rss_kib": None, "loop_drift_ms": 0.0,
                "asyncio_tasks": 1, "calls": {}}
        self.assertIn("rss_kib=unavailable", pm.format_snapshot(snap))

    def test_rss_parsed_from_status(self):
        with mock.patch("builtins.open", mock.mock_open(read_data="Name:\tx\nVmRSS:\t  2048 kB\n")):
            self.assertEqual(pm.read_rss_kib(), 2048)

    def test_labels_are_bounded(self):
        for i in range(500):
            pm.record_call(f"AAPL-{i}", 0.01)
        pm.record_call("holdings_import", 0.1)
        self.assertEqual(set(pm._calls), {"other", "holdings_import"})
        self.assertEqual(pm._calls["other"]["count"], 500)

    def test_timed_call_records_on_exception(self):
        with self.assertRaises(RuntimeError):
            with pm.timed_call("policy_resolution"):
                raise RuntimeError("x")
        self.assertEqual(pm._calls["policy_resolution"]["count"], 1)

    def test_loop_logs_summary_and_cancels(self):
        async def run():
            with self.assertLogs("utils.performance_metrics", level="INFO") as logs:
                task = pm.start_metrics_task(True, 1)
                self.assertIs(pm.start_metrics_task(True, 1), task)  # no duplicate
                await asyncio.sleep(1.3)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            return logs.output

        output = asyncio.run(run())
        self.assertEqual(len(output), 1)
        self.assertIn("resource_metrics", output[0])

    def test_background_tasks_start_and_stop_metrics(self):
        async def run():
            with mock.patch.object(tasks, "_start_reminder_scheduler", return_value=mock.Mock()), \
                 mock.patch.object(tasks, "reschedule_queued_orders", new=mock.AsyncMock()), \
                 mock.patch.object(tasks, "RESOURCE_METRICS_ENABLED", True), \
                 mock.patch.object(tasks, "RESOURCE_METRICS_INTERVAL_SECONDS", 60):
                first = await tasks.start_background_tasks(mock.Mock())
                second = await tasks.start_background_tasks(mock.Mock())
                self.assertIs(first.metrics_task, second.metrics_task)
                await tasks.stop_background_tasks(first)
                return first.metrics_task.cancelled()

        self.assertTrue(asyncio.run(run()))

    def test_metrics_task_absent_when_disabled(self):
        async def run():
            with mock.patch.object(tasks, "_start_reminder_scheduler", return_value=mock.Mock()), \
                 mock.patch.object(tasks, "reschedule_queued_orders", new=mock.AsyncMock()):
                bg = await tasks.start_background_tasks(mock.Mock())
                await tasks.stop_background_tasks(bg)
                return bg.metrics_task

        self.assertIsNone(asyncio.run(run()))


if __name__ == "__main__":
    unittest.main()
