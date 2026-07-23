"""Primary-channel error watcher that can invoke Codex for auto-remediation."""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from discord.ext import commands

from utils.config_utils import (
    AUTO_RSA_DIR,
    AUTO_RSA_ERROR_WATCHER_COOLDOWN_SECONDS,
    AUTO_RSA_ERROR_WATCHER_ENABLED,
    AUTO_RSA_ERROR_WATCHER_MAX_OUTPUT_CHARS,
    AUTO_RSA_ERROR_WATCHER_TIMEOUT_SECONDS,
    CODEX_EXEC_COMMAND,
    DISCORD_PRIMARY_CHANNEL,
)
from utils.logging_setup import logger

_ERROR_KEYWORDS = (
    "error",
    "exception",
    "traceback",
    "fatal",
    "failed",
    "failure",
    "unable to",
    "permission denied",
)


def _text_has_error_signal(text: str) -> bool:
    """Return ``True`` when ``text`` appears to describe an error condition.

    Args:
        text: Message content or embed text to evaluate.

    Returns:
        ``True`` if the content includes known error markers.
    """

    lowered = (text or "").lower()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in _ERROR_KEYWORDS)


def _extract_message_text(message: Any) -> str:
    """Extract message and embed text from a Discord message-like object."""

    parts = []
    content = getattr(message, "content", "") or ""
    if content.strip():
        parts.append(content.strip())

    for embed in getattr(message, "embeds", []) or []:
        title = getattr(embed, "title", None)
        description = getattr(embed, "description", None)
        if title:
            parts.append(str(title))
        if description:
            parts.append(str(description))

    return "\n".join(parts).strip()


def _resolve_codex_cwd() -> Path:
    """Resolve the working directory used for ``codex exec`` invocations."""

    if AUTO_RSA_DIR:
        candidate = Path(AUTO_RSA_DIR).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
        logger.warning(
            "AUTO_RSA_DIR=%s does not exist or is not a directory; falling back to current working directory.",
            AUTO_RSA_DIR,
        )
    return Path.cwd().resolve()


def _build_codex_prompt(*, error_text: str, message: Any, codex_cwd: Path) -> str:
    """Build a Codex prompt with runtime context and remediation constraints."""

    channel_id = getattr(getattr(message, "channel", None), "id", "unknown")
    author_name = getattr(
        getattr(message, "author", None), "display_name", None
    ) or getattr(getattr(message, "author", None), "name", "unknown")
    message_id = getattr(message, "id", "unknown")
    now_utc = datetime.now(timezone.utc).isoformat()

    write_access = os.access(codex_cwd, os.W_OK)

    return (
        "You are triaging an auto-rsa runtime error from Discord.\n"
        "Evaluate the error, inspect available tools/files, and remediate the issue when possible.\n"
        "If code changes are possible, apply the smallest safe fix and report exactly what changed.\n"
        "If write access is missing or remediation cannot be applied, return:"
        " (1) root-cause summary, (2) step-by-step fix instructions,"
        " and (3) a git-style patch that can be applied manually.\n\n"
        f"Runtime context:\n"
        f"- captured_at_utc: {now_utc}\n"
        f"- discord_channel_id: {channel_id}\n"
        f"- discord_message_id: {message_id}\n"
        f"- discord_author: {author_name}\n"
        f"- execution_cwd: {codex_cwd}\n"
        f"- write_access_to_execution_cwd: {write_access}\n\n"
        f"Error content:\n{error_text}\n"
    )


class PrimaryChannelErrorWatcherCog(commands.Cog):
    """Watch the primary channel for runtime errors and trigger ``codex exec``."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_run_at: datetime | None = None

    def _cooldown_active(self) -> bool:
        """Return ``True`` when the watcher is inside the configured cooldown."""

        if not self._last_run_at:
            return False
        elapsed = (datetime.now(timezone.utc) - self._last_run_at).total_seconds()
        return elapsed < max(0, AUTO_RSA_ERROR_WATCHER_COOLDOWN_SECONDS)

    async def _invoke_codex_exec(self, prompt: str, cwd: Path) -> str:
        """Run ``codex exec`` in a worker thread and return captured output."""

        cmd = shlex.split(CODEX_EXEC_COMMAND)
        if not cmd:
            raise RuntimeError(
                "CODEX_EXEC_COMMAND is empty; expected a command such as 'codex exec'."
            )
        cmd.append(prompt)

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=max(10, AUTO_RSA_ERROR_WATCHER_TIMEOUT_SECONDS),
                check=False,
            )

        completed = await asyncio.to_thread(_run)
        output = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if completed.returncode != 0:
            logger.error(
                "codex exec returned %s: %s", completed.returncode, stderr or output
            )

        if output and stderr:
            return f"{output}\n\n[stderr]\n{stderr}"
        return output or stderr or "No output from codex exec."

    @commands.Cog.listener()
    async def on_message(self, message):
        """Watch primary-channel messages and trigger Codex remediation on errors."""

        if not AUTO_RSA_ERROR_WATCHER_ENABLED:
            return

        if (
            DISCORD_PRIMARY_CHANNEL
            and getattr(message.channel, "id", None) != DISCORD_PRIMARY_CHANNEL
        ):
            return

        if message.author == self.bot.user:
            return

        error_text = _extract_message_text(message)
        if not _text_has_error_signal(error_text):
            return

        if self._cooldown_active():
            logger.info(
                "Primary-channel error watcher cooldown active; skipping message %s",
                getattr(message, "id", "unknown"),
            )
            return

        self._last_run_at = datetime.now(timezone.utc)
        codex_cwd = _resolve_codex_cwd()
        prompt = _build_codex_prompt(
            error_text=error_text, message=message, codex_cwd=codex_cwd
        )

        logger.info(
            "Primary-channel error watcher invoking codex exec for message %s",
            getattr(message, "id", "unknown"),
        )

        try:
            result = await self._invoke_codex_exec(prompt, codex_cwd)
        except Exception as exc:
            logger.exception(
                "Primary-channel error watcher failed to execute codex: %s", exc
            )
            await message.channel.send(
                "auto-rsa error watcher failed to run codex exec. "
                "Check CODEX_EXEC_COMMAND and runtime permissions."
            )
            return

        max_chars = max(200, AUTO_RSA_ERROR_WATCHER_MAX_OUTPUT_CHARS)
        trimmed = result[:max_chars]
        if len(result) > max_chars:
            trimmed += "\n... (truncated)"

        await message.channel.send(
            "Auto-rsa error watcher result from codex exec:\n" f"```\n{trimmed}\n```"
        )


async def setup(bot: commands.Bot) -> None:
    """Register the primary-channel error watcher cog."""

    await bot.add_cog(PrimaryChannelErrorWatcherCog(bot))
