"""Tests for sent-order command logging and reporting commands."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from datetime import datetime

from rsassistant.bot.cogs.orders import OrdersCog
from utils import order_exec
from utils.market_calendar import MARKET_TZ


class DummyCtx:
    """Capture outbound Discord messages for assertions."""

    def __init__(self):
        self.messages = []

    async def send(self, message, **kwargs):  # noqa: D401 - passthrough helper
        """Store sent message text."""

        self.messages.append(message)


class OrderSendCommandsTest(IsolatedAsyncioTestCase):
    """Verify sent-order logging and retrieval commands."""

    async def test_send_sell_command_records_sent_rsa_entry(self):
        """Sending a canonical !rsa command should write an audit entry."""

        channel = SimpleNamespace(send=AsyncMock(), id=777)

        with patch.object(
            order_exec, "record_sent_rsa_order"
        ) as record_mock, patch.object(
            order_exec,
            "_schedule_closed_market_order",
            new=AsyncMock(return_value=False),
        ), patch.object(
            order_exec, "_await_rsa_rate_limit", new=AsyncMock()
        ):
            await order_exec.send_sell_command(channel, "!rsa buy 2 TSLA all false")

        channel.send.assert_awaited_once_with("!rsa buy 2 TSLA all false")
        record_mock.assert_called_once()
        self.assertEqual(record_mock.call_args.kwargs["ticker"], "TSLA")

    async def test_failed_discord_send_keeps_queued_order(self):
        channel = SimpleNamespace(
            send=AsyncMock(side_effect=RuntimeError("discord unavailable")), id=777
        )
        order_id = "stable-uuid"
        with patch.object(order_exec, "add_to_order_queue") as add_mock, patch.object(
            order_exec, "remove_order"
        ) as remove_mock, patch.object(
            order_exec, "is_market_open_at", return_value=True
        ), patch.object(order_exec, "_await_rsa_rate_limit", new=AsyncMock()):
            await order_exec.schedule_and_execute(
                channel,
                action="buy",
                ticker="TSLA",
                quantity=1,
                broker="all",
                execution_time=datetime.now(MARKET_TZ),
                order_id=order_id,
            )

        add_mock.assert_called_once()
        remove_mock.assert_not_called()

    async def test_orders_command_formats_recent_entries(self):
        """..orders should render recent send log entries in descending order."""

        ctx = DummyCtx()
        cog = OrdersCog(SimpleNamespace(loop=asyncio.get_running_loop()))
        entries = [
            {
                "sent_at": "2026-01-01T10:02:00+00:00",
                "action": "sell",
                "quantity": 1,
                "ticker": "TSLA",
                "broker": "rh",
                "channel_id": "456",
            }
        ]
        with patch(
            "rsassistant.bot.cogs.orders.list_sent_rsa_orders", return_value=entries
        ):
            await OrdersCog.list_sent_orders.callback(cog, ctx, "TSLA", "sell")

        self.assertEqual(len(ctx.messages), 1)
        self.assertIn("Recently Sent !rsa Orders", ctx.messages[0])
        self.assertIn("SELL 1 TSLA via rh", ctx.messages[0])

    async def test_lastorder_command_handles_missing_ticker_entry(self):
        """..lastorder <ticker> should report when no entry exists."""

        ctx = DummyCtx()
        cog = OrdersCog(SimpleNamespace(loop=asyncio.get_running_loop()))

        with patch(
            "rsassistant.bot.cogs.orders.latest_sent_rsa_order", return_value=None
        ):
            await OrdersCog.show_last_sent_order.callback(cog, ctx, "NVDA")

        self.assertEqual(ctx.messages, ["No sent !rsa orders found for NVDA."])
