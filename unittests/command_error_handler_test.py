"""Tests covering the shared command error handler."""

import unittest
from typing import Optional

from discord.ext import commands

import RSAssistant


class DummyCommand:
    """Lightweight stand-in for a Discord command object."""

    def __init__(self, qualified_name: str, usage: Optional[str] = None, signature: str = ""):
        self.qualified_name = qualified_name
        self.usage = usage
        self.signature = signature

    def has_error_handler(self) -> bool:  # noqa: D401 - interface parity with discord.py
        """Match the discord.py command API for local error handlers."""

        return False


class DummyCtx:
    """Capture outbound messages from the error handler."""

    def __init__(self, prefix: Optional[str], command: Optional[DummyCommand]):
        self.prefix = prefix
        self.command = command
        self.messages = []
        self.invoked_with = command.qualified_name if command else None

    async def send(self, message, **kwargs):  # noqa: D401 - passthrough for testing
        """Capture messages instead of sending to Discord."""

        self.messages.append(message)


class CommandErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    """Ensure ``on_command_error`` communicates correct usage details."""

    async def test_usage_message_uses_command_usage_field(self):
        command = DummyCommand("liquidate", usage="<broker> [test_mode]")
        ctx = DummyCtx(prefix="..", command=command)

        await RSAssistant.on_command_error(ctx, commands.UserInputError("missing args"))

        self.assertEqual(
            ["Incorrect arguments. Usage: `..liquidate <broker> [test_mode]`"],
            ctx.messages,
        )

    async def test_usage_message_falls_back_to_signature_and_prefix(self):
        command = DummyCommand("restart", usage=None, signature="[delay]")
        ctx = DummyCtx(prefix=None, command=command)

        await RSAssistant.on_command_error(ctx, commands.UserInputError("bad args"))

        expected_prefix = RSAssistant.BOT_PREFIX
        self.assertEqual(
            [f"Incorrect arguments. Usage: `{expected_prefix}restart [delay]`"],
            ctx.messages,
        )

    async def test_command_not_found_does_not_emit_message(self):
        ctx = DummyCtx(prefix="..", command=None)

        await RSAssistant.on_command_error(ctx, commands.CommandNotFound("unknown"))

        self.assertEqual([], ctx.messages)


if __name__ == "__main__":  # pragma: no cover - convenience for direct execution
    unittest.main()
