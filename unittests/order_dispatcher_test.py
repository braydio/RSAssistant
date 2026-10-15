import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from rsassistant.persistence import orders as _orders  # noqa: F401
from utils import order_dispatcher as od
from utils import order_queue_manager as oq
from utils.market_calendar import MARKET_TZ

FIXED_NOW = datetime(2026, 10, 14, 10, 0, 0, tzinfo=MARKET_TZ)  # Wednesday, market open


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class DispatcherTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target in (oq,):
            p = mock.patch.object(target, "DATABASE_PATH", Path(self.tmp.name) / "q.db")
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(oq, "QUEUE_FILE", Path(self.tmp.name) / "none.json")
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(od, "is_market_open_at", return_value=True)
        p.start()
        self.addCleanup(p.stop)
        self.sent = []
        self.now = FIXED_NOW

        async def send(order):
            self.sent.append(order.order_id)
            return True

        self.send = send
        self.disp = od.OrderDispatcher(send=send, clock=lambda: self.now)

    async def asyncTearDown(self):
        await self.disp.stop()

    def _add(self, oid, when, state="pending"):
        oq.add_to_order_queue(
            oid,
            {"action": "buy", "ticker": "AAA", "quantity": 1, "broker": "all",
             "time": _fmt(when), "status": state},
        )

    def _reg(self, oid, ctx=None):
        self.disp.register(od.PendingOrder(oid, "buy", "AAA", 1, "all", ctx))

    async def test_hundred_orders_use_one_task(self):
        before = len(asyncio.all_tasks())
        for i in range(100):
            self._add(f"o{i}", FIXED_NOW + timedelta(days=3, minutes=i))
            self._reg(f"o{i}")
        await asyncio.sleep(0)
        self.assertEqual(len(asyncio.all_tasks()) - before, 1)
        self.assertEqual(self.disp.registered_count, 100)

    async def test_scan_next_due_and_due_now(self):
        self._add("later", FIXED_NOW + timedelta(hours=2))
        self._add("now", FIXED_NOW - timedelta(seconds=1))
        self._reg("later")
        self._reg("now")
        due, wait = self.disp.scan()
        self.assertEqual([o.order_id for o in due], ["now"])
        self.assertAlmostEqual(wait, 7200, delta=1)

    async def test_dispatch_sends_once_and_removes(self):
        self._add("a", FIXED_NOW)
        order = od.PendingOrder("a", "buy", "AAA", 1, "all", None)
        results = await asyncio.gather(self.disp.dispatch(order), self.disp.dispatch(order))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.sent, ["a"])
        self.assertNotIn("a", oq.get_order_queue())

    async def test_cancelled_order_never_sent(self):
        self._add("c", FIXED_NOW - timedelta(seconds=1))
        self._reg("c")
        oq.remove_order("c")
        due, _ = self.disp.scan()
        self.assertEqual(due, [])
        self.assertEqual(self.disp.registered_count, 0)

    async def test_failed_send_keeps_order_pending(self):
        async def fail(order):
            return False

        disp = od.OrderDispatcher(send=fail, clock=lambda: self.now)
        self._add("f", FIXED_NOW)
        self.assertFalse(await disp.dispatch(od.PendingOrder("f", "buy", "AAA", 1, "all", None)))
        self.assertIn("f", oq.get_order_queue())
        self.assertEqual(oq.get_scheduled_states(["f"])["f"][1], "pending")

    async def test_raised_send_is_parked_not_resent(self):
        async def boom(order):
            raise RuntimeError("after send?")

        disp = od.OrderDispatcher(send=boom, clock=lambda: self.now)
        self._add("x", FIXED_NOW)
        await disp.dispatch(od.PendingOrder("x", "buy", "AAA", 1, "all", None))
        self.assertEqual(oq.get_scheduled_states(["x"])["x"][1], "needs_review")
        self.assertEqual(await disp.dispatch(od.PendingOrder("x", "buy", "AAA", 1, "all", None)), False)
        self.assertEqual(oq.get_order_queue()["x"]["state"], "needs_review")

    async def test_restart_recovery_parks_dispatching(self):
        self._add("s", FIXED_NOW)
        self.assertEqual(oq.claim_order("s"), oq.CLAIM_CLAIMED)
        self.assertEqual(oq.recover_stale_dispatching(), ["s"])
        self.assertEqual(oq.get_scheduled_states(["s"])["s"][1], "needs_review")
        self.assertEqual(oq.claim_order("s"), oq.CLAIM_BUSY)

    async def test_claim_contention_and_missing(self):
        self._add("k", FIXED_NOW)
        self.assertEqual(oq.claim_order("k"), oq.CLAIM_CLAIMED)
        self.assertEqual(oq.claim_order("k"), oq.CLAIM_BUSY)
        self.assertEqual(oq.claim_order("nope"), oq.CLAIM_MISSING)

    async def test_duplicate_registration_keeps_single_entry(self):
        self._add("d", FIXED_NOW + timedelta(hours=1))
        for _ in range(5):
            self._reg("d")
        self.assertEqual(self.disp.registered_count, 1)

    async def test_run_loop_dispatches_when_woken_and_goes_idle(self):
        self._add("r", FIXED_NOW - timedelta(seconds=1))
        self._reg("r")
        for _ in range(50):
            await asyncio.sleep(0.01)
            if self.sent:
                break
        self.assertEqual(self.sent, ["r"])
        await asyncio.sleep(0.05)
        self.assertTrue(self.disp._task.done())  # no idle task once the queue is empty

    async def test_market_closed_defers_to_next_open(self):
        next_open = FIXED_NOW + timedelta(days=1)
        with mock.patch.object(od, "is_market_open_at", return_value=False), \
            mock.patch.object(od, "next_market_open", return_value=next_open):
            eff = od.effective_execution_time(FIXED_NOW - timedelta(hours=5), FIXED_NOW)
        self.assertEqual(eff, next_open)


if __name__ == "__main__":
    unittest.main()


class AdapterTest(DispatcherTest):
    """schedule_and_execute compatibility adapter on top of the dispatcher."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        from utils import order_exec

        self.oe = order_exec
        for name, value in (
            ("_dispatcher", self.disp),
            ("is_market_open_at", True),
        ):
            target = mock.patch.object(
                order_exec, name, value if name == "_dispatcher" else mock.Mock(return_value=True)
            )
            target.start()
            self.addCleanup(target.stop)
        p = mock.patch.object(order_exec, "send_sell_command", new=mock.AsyncMock(return_value=True))
        self.send_cmd = p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(order_exec, "datetime", wraps=datetime)
        dt = p.start()
        dt.now.return_value = FIXED_NOW
        self.addCleanup(p.stop)

    async def test_future_order_registers_without_sleeping_task(self):
        before = len(asyncio.all_tasks())
        for i in range(20):
            await self.oe.schedule_and_execute(
                object(), "buy", "AAA", 1, "all", FIXED_NOW + timedelta(days=2, minutes=i)
            )
        await asyncio.sleep(0)
        self.assertEqual(len(asyncio.all_tasks()) - before, 1)
        self.assertEqual(len(oq.get_order_queue()), 20)
        self.send_cmd.assert_not_awaited()

    async def test_due_now_sends_inline_and_clears_queue(self):
        await self.oe.schedule_and_execute(object(), "buy", "AAA", 2, "all", FIXED_NOW, order_id="now1")
        self.send_cmd.assert_awaited_once()
        self.assertIn("!rsa buy 2 AAA all false", self.send_cmd.await_args.args[1])
        self.assertNotIn("now1", oq.get_order_queue())

    async def test_rehydrated_but_removed_order_not_sent(self):
        await self.oe.schedule_and_execute(
            object(), "buy", "AAA", 2, "all", FIXED_NOW, order_id="gone", add_to_queue=False
        )
        self.send_cmd.assert_not_awaited()

    async def test_failed_send_leaves_pending(self):
        self.send_cmd.return_value = False
        await self.oe.schedule_and_execute(object(), "buy", "AAA", 2, "all", FIXED_NOW, order_id="fail1")
        self.assertEqual(oq.get_scheduled_states(["fail1"])["fail1"][1], "pending")
