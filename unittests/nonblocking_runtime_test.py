import asyncio
import threading
import time
import unittest
from unittest import mock

from rsassistant.bot.handlers import on_message
from utils import watch_utils


async def _heartbeat_during(coro, ticks=5):
    """Run ``coro`` while counting event-loop ticks; returns (result, ticks)."""
    count = 0
    done = asyncio.Event()

    async def beat():
        nonlocal count
        while not done.is_set():
            count += 1
            await asyncio.sleep(0.005)

    task = asyncio.create_task(beat())
    try:
        result = await coro
    finally:
        done.set()
        await task
    return result, count


class _Ctx:
    def __init__(self):
        self.send = mock.AsyncMock()


class NonBlockingRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_watchlist_prices_fetched_once_off_loop(self):
        calls = []

        def slow_prices(tickers):
            calls.append((threading.get_ident(), tuple(tickers)))
            time.sleep(0.1)
            return {t: 1.0 for t in tickers}

        manager = watch_utils.WatchListManager()
        wl = {"AAA": {"split_date": "x", "split_ratio": "1-2"}, "BBB": {}}
        ctx = _Ctx()
        with mock.patch.object(manager, "get_watch_list", return_value=wl), \
            mock.patch.object(watch_utils, "get_last_prices", slow_prices):
            _, ticks = await _heartbeat_during(manager.send_watchlist_prices(ctx))
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0][0], threading.get_ident())
        self.assertEqual(set(calls[0][1]), {"AAA", "BBB"})
        self.assertGreater(ticks, 3)
        ctx.send.assert_awaited()

    async def test_secondary_channel_parse_off_loop_and_failure_is_bounded(self):
        message = mock.Mock(content="msg", channel=mock.Mock())
        seen = {}

        def slow_alert(content):
            seen["thread"] = threading.get_ident()
            time.sleep(0.1)
            return {"ticker": None, "url": None, "reverse_split_confirmed": False}

        with mock.patch.object(on_message, "alert_channel_message", slow_alert):
            _, ticks = await _heartbeat_during(
                on_message.handle_secondary_channel(mock.Mock(), message)
            )
        self.assertNotEqual(seen["thread"], threading.get_ident())
        self.assertGreater(ticks, 3)

        def boom(content):
            raise RuntimeError("net down")

        with mock.patch.object(on_message, "alert_channel_message", boom), \
            mock.patch.object(on_message, "_process_round_up_flow", mock.AsyncMock()) as flow:
            await on_message.handle_secondary_channel(mock.Mock(), message)
        flow.assert_not_called()

    async def test_policy_analyses_bounded_to_two_concurrent(self):
        active = 0
        peak = 0
        lock = threading.Lock()

        def alert(content):
            return {"ticker": "AAA", "url": "http://x", "reverse_split_confirmed": True}

        def analysis(url, ticker_hint=None, fallback_text=None):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return None

        message = mock.Mock(content="m", channel=mock.Mock())
        with mock.patch.object(on_message, "alert_channel_message", alert), \
            mock.patch.object(on_message, "resolve_message_destination"), \
            mock.patch.object(on_message.OnMessagePolicyResolver, "full_analysis", analysis):
            await asyncio.gather(
                *(on_message.handle_secondary_channel(mock.Mock(), message) for _ in range(6))
            )
        self.assertLessEqual(peak, 2)


if __name__ == "__main__":
    unittest.main()
