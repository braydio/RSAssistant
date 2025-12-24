"""Core bot bootstrapper and cog loader.

This module wires up Discord intents, loads the core cogs defined under
``bot/cogs`` and spins up background tasks from :mod:`bot.tasks`. Optional
plugins can be enabled via the ``ENABLED_PLUGINS`` environment variable, where
values are provided as a comma-separated list (e.g., ``ENABLED_PLUGINS=ultma``).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from typing import Iterable

import discord
import discord.gateway
from discord.ext import commands

from bot import tasks as task_runner
from utils.config_utils import BOT_PREFIX, BOT_TOKEN
from utils.logging_setup import setup_logging

__all__ = ["RSAssistantBot", "create_bot", "run_bot"]

_CORE_COGS: tuple[str, ...] = (
    "bot.cogs.watchlist",
    "bot.cogs.orders",
    "bot.cogs.holdings",
    "bot.cogs.split_monitor",
)

discord.gateway.DiscordWebSocket.resume_timeout = 60
discord.gateway.DiscordWebSocket.gateway_timeout = 60

setup_logging()
logger = logging.getLogger(__name__)


def _parse_enabled_plugins(raw: str | None) -> list[str]:
    """Return sanitized plugin identifiers from ``raw``."""

    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


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
