"""Tests for queued order rescheduling tasks."""

import asyncio
from datetime import datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from rsassistant.bot import tasks


class DummyChannel:
    """Minimal async channel stub for Discord operations."""

    def __init__(self):
        self.send = AsyncMock()


class OrderQueueTasksTest(IsolatedAsyncioTestCase):
    """Validate past-due queue rescheduling behavior."""

    async def test_reschedule_past_due_orders_updates_time_and_schedules(self):
        past_time = "2025-01-01 09:30:00"
        queued = {
            "TEST_20250101_0930_buy": {
                "action": "buy",
                "ticker": "TEST",
                "quantity": 1,
                "broker": "all",
                "time": past_time,
            }
        }
        channel = DummyChannel()
        next_open = datetime(2025, 1, 2, 9, 30)

        class DummyBot:
            def __init__(self, loop):
                self.loop = loop

        bot = DummyBot(asyncio.get_running_loop())

        with patch.object(tasks, "get_order_queue", return_value=queued), patch.object(
            tasks, "resolve_reply_channel", return_value=channel
        ), patch.object(
            tasks, "is_market_open_at", return_value=False
        ), patch.object(
            tasks, "next_market_open", return_value=next_open
        ), patch.object(
            tasks, "update_order_time", return_value=True
        ) as update_mock, patch.object(
            tasks, "schedule_and_execute", new=AsyncMock()
        ) as schedule_mock:
            await tasks.reschedule_past_due_orders(bot=bot)

        update_mock.assert_called_once_with(
            "TEST_20250101_0930_buy", "2025-01-02 09:30:00"
        )
        schedule_mock.assert_awaited_once()
