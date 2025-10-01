"""Tests covering validation for the ``..ord`` command."""

import unittest
from discord.ext import commands

import RSAssistant


class DummyCtx:
    """Capture messages sent during command execution."""

    def __init__(self):
        self.messages = []

    async def send(self, message, **kwargs):  # noqa: D401 - passthrough for testing
        """Store outbound Discord messages for later assertions."""

        self.messages.append(message)


EXPECTED_MESSAGE = (
    f"Invalid arguments. Expected format: `{RSAssistant.ORD_COMMAND_USAGE}`"
)


class ProcessOrderCommandTests(unittest.IsolatedAsyncioTestCase):
    """Ensure ``..ord`` validation communicates expected usage."""

    async def test_invalid_action_shows_usage(self):
        ctx = DummyCtx()

        await RSAssistant.process_order(ctx, "hold", ticker="tsla")

        self.assertEqual([EXPECTED_MESSAGE], ctx.messages)

    async def test_missing_ticker_shows_usage(self):
        ctx = DummyCtx()

        await RSAssistant.process_order(ctx, "buy", ticker=None)

        self.assertEqual([EXPECTED_MESSAGE], ctx.messages)

    async def test_invalid_quantity_shows_usage(self):
        ctx = DummyCtx()

        await RSAssistant.process_order(ctx, "sell", ticker="abc", quantity=0)

        self.assertEqual([EXPECTED_MESSAGE], ctx.messages)

    async def test_error_handler_on_bad_argument(self):
        ctx = DummyCtx()

        await RSAssistant.process_order_error(
            ctx, commands.BadArgument("quantity")
        )

        self.assertEqual([EXPECTED_MESSAGE], ctx.messages)


if __name__ == "__main__":  # pragma: no cover - convenience for direct execution
    unittest.main()
