import inspect
import unittest
from unittest import mock

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from rsassistant.bot import tasks
from utils.refresh_scheduler import MARKET_TZ


class SchedulerLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tasks._reminder_scheduler = None

    async def asyncTearDown(self):
        if tasks._reminder_scheduler is not None:
            tasks._reminder_scheduler.shutdown(wait=False)
        tasks._reminder_scheduler = None

    def _start(self, holdings=True):
        with mock.patch.object(tasks, "AUTO_RSA_HOLDINGS_ENABLED", holdings):
            return tasks._start_reminder_scheduler(mock.Mock())

    async def test_jobs_use_asyncio_scheduler_and_market_times(self):
        sched = self._start()
        self.assertIsInstance(sched, AsyncIOScheduler)
        jobs = {j.id: j for j in sched.get_jobs()}
        self.assertEqual(
            set(jobs),
            {"reminder_morning", "reminder_afternoon", "reschedule_past_due_orders", "holdings_import"},
        )
        for job_id, (h, m) in {
            "reminder_morning": (8, 45),
            "reminder_afternoon": (15, 30),
            "reschedule_past_due_orders": (7, 0),
        }.items():
            fields = {f.name: str(f) for f in jobs[job_id].trigger.fields}
            self.assertEqual((fields["hour"], fields["minute"]), (str(h), str(m)))
            self.assertEqual(str(jobs[job_id].trigger.timezone), str(MARKET_TZ))
            self.assertEqual(jobs[job_id].max_instances, 1)
            self.assertTrue(jobs[job_id].coalesce)
            self.assertTrue(inspect.iscoroutinefunction(jobs[job_id].func))

    async def test_holdings_job_only_when_enabled(self):
        sched = self._start(holdings=False)
        self.assertIsNone(sched.get_job("holdings_import"))

    async def test_duplicate_start_returns_same_scheduler(self):
        first = self._start()
        self.assertIs(self._start(), first)
        self.assertEqual(len(first.get_jobs()), 4)

    async def test_holdings_import_runs_off_event_loop(self):
        seen = {}
        loop_thread = __import__("threading").get_ident()

        def fake():
            seen["thread"] = __import__("threading").get_ident()

        with mock.patch.object(tasks, "import_holdings_if_updated", fake):
            await tasks._import_holdings_job()
        self.assertNotEqual(seen["thread"], loop_thread)

    async def test_dst_next_fire_stays_at_local_time(self):
        from datetime import datetime

        sched = self._start()
        job = sched.get_job("reminder_morning")
        for day in ("2026-03-07 12:00", "2026-11-01 12:00"):
            now = MARKET_TZ.localize(datetime.strptime(day, "%Y-%m-%d %H:%M")) if hasattr(MARKET_TZ, "localize") else datetime.strptime(day, "%Y-%m-%d %H:%M").replace(tzinfo=MARKET_TZ)
            nxt = job.trigger.get_next_fire_time(None, now)
            self.assertEqual((nxt.hour, nxt.minute), (8, 45))

    async def test_stop_is_graceful_and_clears_singleton(self):
        sched = self._start()
        bg = tasks.BackgroundTasks(reminder_scheduler=sched)
        await tasks.stop_background_tasks(bg)
        await tasks.stop_background_tasks(bg)  # second stop must not raise
        self.assertIsNone(tasks._reminder_scheduler)

    def test_listener_never_raises(self):
        event = mock.Mock(code=tasks.EVENT_JOB_ERROR, job_id="x", exception=ValueError("secret"))
        with self.assertLogs(tasks.logger, "ERROR") as logs:
            tasks._log_job_event(event)
        self.assertNotIn("secret", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
