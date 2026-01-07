"""Discord cog that wires ULT-MA into the RSAssistant bot when enabled."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from discord.ext import commands

from plugins.ultma.config import (
    AUTO_RSA_API_KEY,
    AUTO_RSA_BASE_URL,
    ENABLE_AUTOMATED_TRADING,
    TRADING_PRICE_CHECK_INTERVAL_SECONDS,
    TRADING_TRAILING_BUFFER,
)
from plugins.ultma.executor import TradeExecutor
from plugins.ultma.state import TradingStateStore
from plugins.ultma.ult_ma_bot import StrategyMetrics, UltMaTradingBot
from utils.config_utils import VOLUMES_DIR

logger = logging.getLogger(__name__)
STATE_DB_PATH = VOLUMES_DIR / "db" / "ultma_state.db"


class UltMaPluginCog(commands.Cog):
    """Exposes Discord commands and lifecycle hooks for the ULT-MA plugin."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()
        executor = TradeExecutor(AUTO_RSA_BASE_URL, AUTO_RSA_API_KEY)
        store = TradingStateStore(STATE_DB_PATH)
        price_check_interval = timedelta(seconds=TRADING_PRICE_CHECK_INTERVAL_SECONDS)
        self.trading_bot = UltMaTradingBot(
            executor=executor,
            state_store=store,
            price_check_interval=price_check_interval,
            trailing_buffer=TRADING_TRAILING_BUFFER,
            on_error=self._on_error,
        )

    async def cog_load(self) -> None:
        if ENABLE_AUTOMATED_TRADING:
            await self._start_trading("configuration")

    async def cog_unload(self) -> None:
        await self.trading_bot.stop()

    async def _start_trading(self, source: str) -> None:
        async with self._lock:
            await self.trading_bot.start()
        logger.info("ULT-MA trading bot started (%s)", source)

    async def _stop_trading(self) -> None:
        async with self._lock:
            await self.trading_bot.stop()
        logger.info("ULT-MA trading bot stopped")

    def _on_error(self, message: str) -> None:
        logger.error("ULT-MA error: %s", message)

    def _format_metrics(self, metrics: StrategyMetrics) -> str:
        next_check = (
            metrics.next_check_at.strftime("%Y-%m-%d %H:%M:%S %Z")
            if metrics.next_check_at
            else "pending"
        )
        symbol_line = "None"
        active = self.trading_bot.active_position()
        if active:
            symbol_line = (
                f"{active.symbol} {active.direction} {active.quantity} @ {active.entry_price}"
            )
        return "\n".join(
            [
                f"Auto trading: {'enabled' if ENABLE_AUTOMATED_TRADING else 'disabled'}",
                f"Paused: {metrics.paused}",
                f"Last color: {metrics.last_color or 'unknown'}",
                f"Previous action: {metrics.previous_color or 'unknown'}",
                f"Last trade direction: {metrics.last_trade_direction or 'none'}",
                f"Next check: {next_check}",
                f"Active position: {symbol_line}",
            ]
        )

    async def _send_status(self, ctx: commands.Context) -> None:
        metrics = self.trading_bot.metrics()
        status = self._format_metrics(metrics)
        await ctx.send(f"```\n{status}\n```")

    @commands.group(name="ultma", invoke_without_command=True)
    async def ultma(self, ctx: commands.Context) -> None:
        """Show the current state of the ULT-MA trading bot."""

        await self._send_status(ctx)

    @ultma.command(name="status")
    async def status(self, ctx: commands.Context) -> None:
        """Force a status refresh from ULT-MA."""

        await self._send_status(ctx)

    @ultma.command(name="start")
    async def start_command(self, ctx: commands.Context) -> None:
        """Start the background ULT-MA monitoring tasks."""

        await self._start_trading("manual")
        await ctx.send("ULT-MA trading tasks started.")

    @ultma.command(name="stop")
    async def stop_command(self, ctx: commands.Context) -> None:
        """Stop the background ULT-MA monitoring tasks."""

        await self._stop_trading()
        await ctx.send("ULT-MA trading tasks stopped.")

    @ultma.command(name="pause")
    async def pause_command(self, ctx: commands.Context) -> None:
        """Pause trading without cancelling the background tasks."""

        self.trading_bot.pause()
        await ctx.send("ULT-MA trading paused.")

    @ultma.command(name="resume")
    async def resume_command(self, ctx: commands.Context) -> None:
        """Resume trading after a pause."""

        self.trading_bot.resume()
        await ctx.send("ULT-MA trading resumed.")

    @ultma.command(name="force")
    async def force_command(self, ctx: commands.Context, direction: str) -> None:
        """Force an entry in the specified direction (long/short)."""

        normalized = direction.lower()
        if normalized not in {"long", "short"}:
            await ctx.send("Direction must be 'long' or 'short'.")
            return
        try:
            await self.trading_bot.force_entry(normalized)
            await ctx.send(f"Forced a {normalized} entry.")
        except Exception as exc:
            logger.exception("Failed to force entry", exc_info=exc)
            await ctx.send(f"Failed to force {normalized} entry: {exc}")


async def setup(bot: commands.Bot) -> None:
    """Discord.py loader entrypoint for the ULT-MA plugin."""

    await bot.add_cog(UltMaPluginCog(bot))
