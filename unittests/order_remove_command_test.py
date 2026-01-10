"""Tests for the remove queued order command."""

import asyncio
from types import SimpleNamespace

from rsassistant.bot.cogs.orders import OrdersCog


class DummyCtx:
    """Capture messages sent during command execution."""

    def __init__(self):
        self.messages = []

    async def send(self, message, **kwargs):  # noqa: D401 - simple passthrough
        """Store outbound Discord messages for later assertions."""

        self.messages.append(message)


def test_remove_with_no_argument_lists_queue(monkeypatch):
    """Calling remove with no args should return a numbered queue list."""

    ctx = DummyCtx()
    cog = OrdersCog(SimpleNamespace())

    monkeypatch.setattr(
        "rsassistant.bot.cogs.orders.list_order_queue_items",
        lambda: [
            (
                "ABC_20240101_0930_buy",
                {
                    "action": "buy",
                    "quantity": 5,
                    "ticker": "ABC",
                    "broker": "demo",
                    "time": "2024-01-01 09:30",
                },
            )
        ],
    )

    asyncio.run(cog.remove_queued_order(ctx, None))

    assert ctx.messages == [
        "**Scheduled Orders:**\n"
        "1. ABC_20240101_0930_buy → buy 5 ABC via demo at 2024-01-01 09:30\n"
        "Type `..remove <number>` to remove an order."
    ]


def test_remove_with_no_argument_and_empty_queue(monkeypatch):
    """Calling remove with no args should report an empty queue."""

    ctx = DummyCtx()
    cog = OrdersCog(SimpleNamespace())
    monkeypatch.setattr("rsassistant.bot.cogs.orders.list_order_queue_items", lambda: [])

    asyncio.run(cog.remove_queued_order(ctx, None))

    assert ctx.messages == ["There are no scheduled orders."]
