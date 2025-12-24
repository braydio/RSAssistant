"""Core bot bootstrapper and cog loader.

This module wires up Discord intents, loads the core cogs defined under
``bot/cogs`` and spins up background tasks from :mod:`bot.tasks`. Optional
plugins can be enabled via the ``ENABLED_PLUGINS`` environment variable, where
values are provided as a comma-separated list (e.g., ``ENABLED_PLUGINS=ultma``).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Iterable

import discord
import discord.gateway
from discord.ext import commands

from . import tasks as task_runner
from utils.channel_resolver import resolve_reply_channel
from utils.config_utils import (
    ACCOUNT_MAPPING,
    BOT_PREFIX,
    BOT_TOKEN,
    DISCORD_PRIMARY_CHANNEL,
    DISCORD_SECONDARY_CHANNEL,
    DISCORD_TERTIARY_CHANNEL,
    EXCEL_FILE_MAIN,
    HOLDINGS_LOG_CSV,
    ORDERS_LOG_CSV,
    SQL_LOGGING_ENABLED,
)
from utils.logging_setup import setup_logging
from utils.on_message_utils import handle_on_message, set_channels
from utils.order_queue_manager import get_order_queue
from utils.sql_utils import init_db

__all__ = ["RSAssistantBot", "create_bot", "run_bot"]

_CORE_COGS: tuple[str, ...] = (
    "rsassistant.bot.cogs.admin",
    "rsassistant.bot.cogs.accounts",
    "rsassistant.bot.cogs.watchlist",
    "rsassistant.bot.cogs.orders",
    "rsassistant.bot.cogs.holdings",
    "rsassistant.bot.cogs.split_monitor",
    "rsassistant.bot.cogs.reporting",
    "rsassistant.bot.cogs.utilities",
)

discord.gateway.DiscordWebSocket.resume_timeout = 60
discord.gateway.DiscordWebSocket.gateway_timeout = 60

logger = logging.getLogger(__name__)
setup_logging()

if SQL_LOGGING_ENABLED:
    init_db()
else:
    logger.info("SQL logging disabled; skipping database initialization.")

logger.info("Holdings Log CSV file: %s", HOLDINGS_LOG_CSV)
logger.info("Orders Log CSV file: %s", ORDERS_LOG_CSV)


def _parse_enabled_plugins(raw: str | None) -> list[str]:
    """Return sanitized plugin identifiers from ``raw``."""

    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _build_command_usage(prefix: str | None, command: commands.Command | None) -> str:
    effective_prefix = (prefix or BOT_PREFIX).strip()
    if command is None:
        return effective_prefix

    qualified_name = getattr(command, "qualified_name", "").strip()
    usage_hint = (
        getattr(command, "usage", None)
        or getattr(command, "signature", "")
        or ""
    ).strip()

    if qualified_name and usage_hint:
        return f"{effective_prefix}{qualified_name} {usage_hint}".strip()
    if qualified_name:
        return f"{effective_prefix}{qualified_name}".strip()
    return effective_prefix


class RSAssistantBot(commands.Bot):
    """Discord bot configured with modular cogs and background tasks."""

    def __init__(self, *, enabled_plugins: Iterable[str] | None = None):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(
            command_prefix=BOT_PREFIX,
            case_insensitive=True,
            intents=intents,
            reconnect=True,
        )
        self.enabled_plugins = list(enabled_plugins or _parse_enabled_plugins(os.getenv("ENABLED_PLUGINS")))
        self.background_tasks = None
        self.help_command = commands.MinimalHelpCommand()

    async def setup_hook(self) -> None:
        await self._load_core_cogs()
        await self._load_plugins()
        self.background_tasks = await task_runner.start_background_tasks(self)

    async def on_ready(self) -> None:
        now = datetime.now()
        logger.info(
            "RSAssistant by @braydio - GitHub: https://github.com/braydio/RSAssistant"
        )
        logger.info("V3.1 | Running in CLI | Runtime Environment: Production")

        channel = resolve_reply_channel(self, DISCORD_PRIMARY_CHANNEL)
        account_setup_message = (
            "**(╯°□°）╯**\n\n"
            "Account mappings not found. Please fill in Reverse Split Log > Account Details sheet at\n"
            f"`{EXCEL_FILE_MAIN}`\n\n"
            "Then run: `..loadmap` and `..loadlog`."
        )
        try:
            ready_message = (
                account_setup_message
                if not ACCOUNT_MAPPING
                else "Watching for order activity o.O"
            )
        except (FileNotFoundError, json.JSONDecodeError):
            ready_message = account_setup_message

        if channel:
            queued = len(get_order_queue())
            await channel.send(
                f"{ready_message}\nTime: {now.strftime('%Y-%m-%d %H:%M:%S')} | Queued orders: {queued}"
            )
        else:
            logger.warning(
                "Target channel not found - ID: %s on startup.",
                DISCORD_PRIMARY_CHANNEL,
            )
        logger.info(
            "%s has connected to Discord! PRIMARY | %s, SECONDARY | %s, | TERTIARY | %s",
            self.user,
            DISCORD_PRIMARY_CHANNEL,
            DISCORD_SECONDARY_CHANNEL,
            DISCORD_TERTIARY_CHANNEL,
        )
        set_channels(
            DISCORD_PRIMARY_CHANNEL,
            DISCORD_SECONDARY_CHANNEL,
            DISCORD_TERTIARY_CHANNEL,
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user:
            logger.info("Message is from myself! %s", self.user)
            return
        if message.content.startswith(BOT_PREFIX):
            logger.info("Handling command %s", message.content)
            await self.process_commands(message)
            return
        await handle_on_message(self, message)

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        command = getattr(ctx, "command", None)
        if command and getattr(command, "on_error", None):
            return

        has_local_handler = False
        if command and callable(getattr(command, "has_error_handler", None)):
            has_local_handler = command.has_error_handler()
        if has_local_handler:
            return

        if isinstance(error, commands.UserInputError):
            usage_text = _build_command_usage(getattr(ctx, "prefix", None), command)
            await ctx.send(f"Incorrect arguments. Usage: `{usage_text}`")
            return

        if isinstance(error, commands.CommandNotFound):
            logger.debug(
                "Command not found during invocation: %s",
                getattr(ctx, "invoked_with", "<unknown>"),
            )
            return

        logger.exception(
            "Unhandled exception while executing command '%s'.",
            getattr(command, "qualified_name", "<unknown>"),
            exc_info=error,
        )
    async def close(self) -> None:
        if self.background_tasks:
            await task_runner.stop_background_tasks(self.background_tasks)
        await super().close()

    async def _load_core_cogs(self) -> None:
        for extension in _CORE_COGS:
            await self._load_extension_safe(extension)

    async def _load_plugins(self) -> None:
        for plugin in self.enabled_plugins:
            module_path = f"plugins.{plugin}.cog"
            await self._load_extension_safe(module_path, is_plugin=True)

    async def _load_extension_safe(self, name: str, *, is_plugin: bool = False) -> None:
        label = "plugin" if is_plugin else "cog"
        try:
            await self.load_extension(name)
            logger.info("Loaded %s '%s'", label, name)
        except commands.ExtensionAlreadyLoaded:
            logger.debug("%s '%s' already loaded", label.title(), name)
        except ModuleNotFoundError:
            logger.warning("Skipped %s '%s' (module not found)", label, name)
        except Exception:
            logger.exception("Failed to load %s '%s'", label, name)


def create_bot(*, enabled_plugins: Iterable[str] | None = None) -> RSAssistantBot:
    """Factory helper to instantiate the configured bot."""

    return RSAssistantBot(enabled_plugins=enabled_plugins)


def run_bot() -> None:
    """Entrypoint for launching the modular bot."""

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is required to start RSAssistant.")
        raise SystemExit(1)

    bot = create_bot()
    try:
        bot.run(BOT_TOKEN)
    finally:
        if bot.is_closed():
            logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    run_bot()
