"""Tests for the primary-channel auto-rsa error watcher cog."""

from __future__ import annotations

import asyncio
import stat
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from rsassistant.bot.cogs import primary_channel_error_watcher as watcher
from rsassistant.bot.cogs.primary_channel_error_watcher import (
    PrimaryChannelErrorWatcherCog,
    _build_codex_prompt,
    _extract_message_text,
    _text_has_error_signal,
)

MOD = "rsassistant.bot.cogs.primary_channel_error_watcher"


class PrimaryChannelErrorWatcherCogTest(IsolatedAsyncioTestCase):
    """Validate watcher filtering, fail-closed setup, and safe output."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        codex = self.dir / "codex"
        codex.write_text("#!/bin/sh\n")
        codex.chmod(codex.stat().st_mode | stat.S_IXUSR)
        self.settings = {
            "AUTO_RSA_ERROR_WATCHER_ENABLED": True,
            "DISCORD_PRIMARY_CHANNEL": 123,
            "AUTO_RSA_ERROR_WATCHER_SENDER_IDS": {456},
            "AUTO_RSA_DIR": str(self.dir),
            "CODEX_EXEC_COMMAND": f"{codex} exec",
            "AUTO_RSA_ERROR_WATCHER_COOLDOWN_SECONDS": 0,
        }

    def _patched(self, **overrides):
        values = {**self.settings, **overrides}
        patchers = [patch(f"{MOD}.{k}", v) for k, v in values.items()]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def _message(self, *, content="ERROR: traceback in order executor",
                 channel_id=123, message_id=22, author_id=456):
        channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        author = SimpleNamespace(id=author_id, name="auto-rsa", display_name="auto-rsa")
        return SimpleNamespace(content=content, embeds=[], channel=channel,
                               author=author, id=message_id)

    def _cog(self):
        return PrimaryChannelErrorWatcherCog(SimpleNamespace(user=SimpleNamespace(id=999)))

    async def test_error_content_runs_triage_and_posts_safe_summary(self):
        self._patched()
        cog, message = self._cog(), self._message()
        raw = "Bearer abcdefghijklmnop1234 PermissionError @everyone"
        with patch.object(cog, "_invoke_codex_exec", new=AsyncMock(return_value=(0, raw, ""))) as run:
            await cog.on_message(message)
        run.assert_awaited_once()
        sent = message.channel.send.await_args
        self.assertNotIn("abcdefghijklmnop1234", sent.args[0])
        self.assertNotIn("@everyone", sent.args[0])
        self.assertNotIn("```", sent.args[0])
        self.assertIsNotNone(sent.kwargs["allowed_mentions"])

    async def test_disabled_and_misconfigured_watchers_never_invoke_codex(self):
        cases = [
            {"AUTO_RSA_ERROR_WATCHER_ENABLED": False},
            {"DISCORD_PRIMARY_CHANNEL": 0},
            {"AUTO_RSA_ERROR_WATCHER_SENDER_IDS": set()},
            {"AUTO_RSA_DIR": ""},
            {"AUTO_RSA_DIR": "/definitely/not/here"},
            {"CODEX_EXEC_COMMAND": "python -c 'print(1)'"},
            {"CODEX_EXEC_COMMAND": f"{self.dir}/codex exec --yolo"},
        ]
        for override in cases:
            with self.subTest(override=override):
                with patch(f"{MOD}.asyncio.create_subprocess_exec") as spawn:
                    cog = self._cog()
                    message = self._message()
                    saved = {k: getattr(watcher, k) for k in override}
                    try:
                        self._apply(override)
                        self._apply({k: v for k, v in self.settings.items() if k not in override})
                        await cog.on_message(message)
                    finally:
                        self._apply(saved)
                spawn.assert_not_called()
                message.channel.send.assert_not_called()

    def _apply(self, values):
        for k, v in values.items():
            setattr(watcher, k, v)

    async def test_wrong_channel_and_sender_ignored(self):
        self._patched()
        cog = self._cog()
        with patch.object(cog, "_invoke_codex_exec", new=AsyncMock(return_value=(0, "", ""))) as run:
            await cog.on_message(self._message(channel_id=1))
            await cog.on_message(self._message(author_id=789, message_id=23))
            await cog.on_message(self._message(content="normal holdings update", message_id=24))
        run.assert_not_called()

    async def test_concurrent_messages_start_one_process(self):
        self._patched()
        cog = self._cog()
        gate = asyncio.Event()

        async def slow(prompt, cwd):
            await gate.wait()
            return 0, "", ""

        m1, m2 = self._message(message_id=1), self._message(message_id=2)
        with patch.object(cog, "_invoke_codex_exec", new=AsyncMock(side_effect=slow)) as run:
            first = asyncio.create_task(cog.on_message(m1))
            await asyncio.sleep(0)
            await cog.on_message(m2)
            gate.set()
            await first
        self.assertEqual(run.await_count, 1)
        m2.channel.send.assert_not_called()

    async def test_duplicate_message_id_and_cooldown(self):
        self._patched(AUTO_RSA_ERROR_WATCHER_COOLDOWN_SECONDS=0)
        cog = self._cog()
        with patch.object(cog, "_invoke_codex_exec", new=AsyncMock(return_value=(0, "", ""))) as run:
            await cog.on_message(self._message(message_id=5))
            await cog.on_message(self._message(message_id=5))
            self.assertEqual(run.await_count, 1)
        self._patched(AUTO_RSA_ERROR_WATCHER_COOLDOWN_SECONDS=600)
        cog = self._cog()
        with patch.object(cog, "_invoke_codex_exec", new=AsyncMock(return_value=(0, "", ""))) as run:
            await cog.on_message(self._message(message_id=6))
            await cog.on_message(self._message(message_id=7))
            self.assertEqual(run.await_count, 1)

    async def test_failure_timeout_and_exception_produce_safe_notices(self):
        self._patched()
        for index, outcome in enumerate([(2, "stderr SECRET=hunter2hunter2", ""), (-1, "", "")]):
            cog = self._cog()
            message = self._message(message_id=100 + index)
            with patch.object(cog, "_invoke_codex_exec", new=AsyncMock(return_value=outcome)):
                await cog.on_message(message)
            text = message.channel.send.await_args.args[0]
            self.assertNotIn("hunter2", text)
            self.assertLessEqual(len(text), 3500)
        cog = self._cog()
        message = self._message(message_id=200)
        with patch.object(cog, "_invoke_codex_exec", new=AsyncMock(side_effect=RuntimeError("SECRET=zzz"))):
            await cog.on_message(message)
        self.assertNotIn("zzz", message.channel.send.await_args.args[0])
        self.assertFalse(cog._lock.locked())

    async def test_invocation_uses_validated_argv_without_shell(self):
        self._patched(CODEX_EXEC_COMMAND=f"{self.dir}/codex exec --full-auto")
        cog = self._cog()
        with patch(f"{MOD}.asyncio.create_subprocess_exec") as spawn:
            with self.assertRaises(ValueError):
                await cog._invoke_codex_exec("prompt", self.dir)
        spawn.assert_not_called()

    async def test_invocation_real_subprocess_is_readonly_and_times_out(self):
        script = self.dir / "codex"
        script.write_text('#!/bin/sh\necho "$@" > "$(dirname "$0")/argv.txt"\n')
        self._patched()
        cog = self._cog()
        code, _, _ = await cog._invoke_codex_exec("the prompt", self.dir)
        self.assertEqual(code, 0)
        argv = (self.dir / "argv.txt").read_text().split()
        self.assertEqual(argv[:5], ["exec", "--sandbox", "read-only", "--ask-for-approval", "never"])
        script.write_text("#!/bin/sh\nsleep 30\n")
        with patch(f"{MOD}.AUTO_RSA_ERROR_WATCHER_TIMEOUT_SECONDS", 0), patch(
            f"{MOD}._MIN_TIMEOUT_SECONDS", 0.2
        ):
            code, _, _ = await cog._invoke_codex_exec("p", self.dir)
        self.assertEqual(code, -1)

    async def test_status_command_hides_values(self):
        self._patched()
        cog = self._cog()
        ctx = SimpleNamespace(send=AsyncMock())
        await cog.watcher_status.callback(cog, ctx)
        text = ctx.send.await_args.args[0]
        self.assertIn("Needs attention: none", text)
        self.assertNotIn(str(self.dir), text)

    def test_extract_message_text_includes_embed_fields(self):
        embed = SimpleNamespace(title="Fatal Error", description="Traceback occurred")
        text = _extract_message_text(SimpleNamespace(content="", embeds=[embed]))
        self.assertIn("Fatal Error", text)
        self.assertIn("Traceback occurred", text)

    def test_error_signal_detection(self):
        self.assertTrue(_text_has_error_signal("Unhandled exception in worker"))
        self.assertFalse(_text_has_error_signal("Heartbeat completed successfully"))

    def test_prompt_treats_discord_error_text_as_untrusted_and_redacts(self):
        prompt = _build_codex_prompt(
            error_text="permission denied token=abcdefghijklmnop1234",
            message=self._message(content="error"),
            codex_cwd=Path("/tmp"),
        )
        self.assertIn("read-only inspection", prompt)
        self.assertIn("<untrusted_error>", prompt)
        self.assertNotIn("abcdefghijklmnop1234", prompt)


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
