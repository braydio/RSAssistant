"""Validation tests for the modular order command."""

import asyncio
import unittest
from types import SimpleNamespace

from rsassistant.bot.cogs.orders import OrdersCog, ORDER_COMMAND_USAGE


class DummyCtx:
    def __init__(self):
        self.messages = []

    async def send(self, message, **kwargs):
        self.messages.append(message)


class ProcessOrderCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_arguments_show_usage(self):
        cog = OrdersCog(SimpleNamespace(loop=asyncio.get_running_loop()))
        for action, ticker, quantity in (
            ("hold", "TSLA", 1),
            ("buy", None, 1),
            ("sell", "ABC", 0),
        ):
            with self.subTest(action=action, ticker=ticker, quantity=quantity):
                ctx = DummyCtx()
                await OrdersCog.process_order.callback(
                    cog, ctx, action, ticker=ticker, quantity=quantity
                )
                self.assertEqual(
                    ctx.messages,
                    [f"Invalid arguments. Expected format: `{ORDER_COMMAND_USAGE}`"],
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
