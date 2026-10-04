"""Tests for the primary-channel auto-rsa error watcher cog."""

from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from rsassistant.bot.cogs.primary_channel_error_watcher import (
    PrimaryChannelErrorWatcherCog,
    _build_codex_prompt,
    _extract_message_text,
    _text_has_error_signal,
)


class PrimaryChannelErrorWatcherCogTest(IsolatedAsyncioTestCase):
    """Validate watcher filtering and Codex invocation behavior."""

    def _build_message(
        self, *, content: str, channel_id: int = 123, message_id: int = 22
    ):
        channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        author = SimpleNamespace(id=456, name="auto-rsa", display_name="auto-rsa")
        return SimpleNamespace(
            content=content,
            embeds=[],
            channel=channel,
            author=author,
            id=message_id,
        )

    async def test_on_message_triggers_codex_for_error_content(self):
        bot = SimpleNamespace(user=SimpleNamespace(id=999))
        cog = PrimaryChannelErrorWatcherCog(bot)
        message = self._build_message(content="ERROR: traceback in order executor")

        with patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.AUTO_RSA_ERROR_WATCHER_ENABLED",
            True,
        ), patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.DISCORD_PRIMARY_CHANNEL",
            123,
        ), patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.AUTO_RSA_ERROR_WATCHER_SENDER_IDS",
            {456},
        ), patch.object(
            cog,
            "_invoke_codex_exec",
            new=AsyncMock(return_value="fixed"),
        ) as codex_mock:
            await cog.on_message(message)

        codex_mock.assert_awaited_once()
        message.channel.send.assert_awaited_once()

    async def test_on_message_skips_non_error_content(self):
        bot = SimpleNamespace(user=SimpleNamespace(id=999))
        cog = PrimaryChannelErrorWatcherCog(bot)
        message = self._build_message(content="normal holdings update")

        with patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.AUTO_RSA_ERROR_WATCHER_ENABLED",
            True,
        ), patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.DISCORD_PRIMARY_CHANNEL",
            123,
        ), patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.AUTO_RSA_ERROR_WATCHER_SENDER_IDS",
            {456},
        ), patch.object(
            cog,
            "_invoke_codex_exec",
            new=AsyncMock(return_value="fixed"),
        ) as codex_mock:
            await cog.on_message(message)

        codex_mock.assert_not_called()
        message.channel.send.assert_not_called()

    async def test_on_message_ignores_sender_outside_allowlist(self):
        bot = SimpleNamespace(user=SimpleNamespace(id=999))
        cog = PrimaryChannelErrorWatcherCog(bot)
        message = self._build_message(content="ERROR: traceback in order executor")

        with patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.AUTO_RSA_ERROR_WATCHER_ENABLED",
            True,
        ), patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.DISCORD_PRIMARY_CHANNEL",
            123,
        ), patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.AUTO_RSA_ERROR_WATCHER_SENDER_IDS",
            {789},
        ), patch.object(
            cog, "_invoke_codex_exec", new=AsyncMock(return_value="diagnosis")
        ) as codex_mock:
            await cog.on_message(message)

        codex_mock.assert_not_called()
        message.channel.send.assert_not_called()

    async def test_codex_invocation_forces_read_only_sandbox(self):
        cog = PrimaryChannelErrorWatcherCog(SimpleNamespace(user=None))
        completed = subprocess.CompletedProcess([], 0, stdout="diagnosis", stderr="")
        with patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.CODEX_EXEC_COMMAND",
            "codex exec --full-auto --sandbox workspace-write",
        ), patch(
            "rsassistant.bot.cogs.primary_channel_error_watcher.subprocess.run",
            return_value=completed,
        ) as run_mock:
            await cog._invoke_codex_exec("untrusted message", Path("/tmp"))

        command = run_mock.call_args.args[0]
        self.assertNotIn("--full-auto", command)
        self.assertIn("--sandbox", command)
        self.assertIn("read-only", command)
        self.assertIn("never", command)

    def test_extract_message_text_includes_embed_fields(self):
        embed = SimpleNamespace(title="Fatal Error", description="Traceback occurred")
        message = SimpleNamespace(content="", embeds=[embed])

        text = _extract_message_text(message)

        self.assertIn("Fatal Error", text)
        self.assertIn("Traceback occurred", text)

    def test_error_signal_detection(self):
        self.assertTrue(_text_has_error_signal("Unhandled exception in worker"))
        self.assertFalse(_text_has_error_signal("Heartbeat completed successfully"))

    def test_prompt_treats_discord_error_text_as_untrusted(self):
        message = self._build_message(content="error")
        prompt = _build_codex_prompt(
            error_text="permission denied",
            message=message,
            codex_cwd=Path("/tmp"),
        )

        self.assertIn("read-only inspection", prompt)
        self.assertIn("<untrusted_error>", prompt)


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
