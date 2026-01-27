"""Watchlist management commands."""

from __future__ import annotations

from discord.ext import commands
from discord.abc import Messageable

from rsassistant.bot.channel_resolver import resolve_watchlist_channel
from utils.watch_utils import watch as handle_watch_command
from utils.watch_utils import watch_list_manager


class WatchlistCog(commands.Cog):
    """Commands for managing watchlist entries and split ratios."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _resolve_watch_context(
        self, ctx: commands.Context
    ) -> commands.Context | Messageable:
        target_channel = resolve_watchlist_channel(self.bot)
        if target_channel and getattr(target_channel, "id", None) != getattr(
            ctx.channel, "id", None
        ):
            await ctx.send("Check the watchlist channel for updates.")
            return target_channel
        return ctx

    @commands.command(
        name="watch",
        aliases=["wa"],
        help="Add ticker(s) to the watchlist.",
        usage="<ticker> <split_date> [split_ratio] | -t <ticker> -d <mm/dd> [-r <ratio>] | <ticker ratio (purchase by mm/dd)>",
        extras={"category": "Watchlist"},
    )
    async def watch(self, ctx: commands.Context, *, text: str) -> None:
        target_ctx = await self._resolve_watch_context(ctx)
        await handle_watch_command(target_ctx, text=text)

    @commands.command(
        name="addratio",
        aliases=["ar"],
        help="Add or update the split ratio for a watched ticker.",
        usage="<ticker> <split_ratio>",
        extras={"category": "Watchlist"},
    )
    async def add_ratio(self, ctx: commands.Context, ticker: str, split_ratio: str) -> None:
        if not split_ratio:
            await ctx.send("Please include split ratio: * X-Y *")
            return
        target_ctx = await self._resolve_watch_context(ctx)
        await watch_list_manager.watch_ratio(target_ctx, ticker, split_ratio)

    @commands.command(
        name="watchlist",
        aliases=["wl"],
        help="List all tickers currently being watched.",
        extras={"category": "Watchlist"},
    )
    async def all_watching(self, ctx: commands.Context) -> None:
        target_ctx = await self._resolve_watch_context(ctx)
        await watch_list_manager.list_watched_tickers(target_ctx, include_prices=True)

    @commands.command(
        name="watched",
        aliases=["ok", "wd"],
        help="Remove a ticker from the watchlist.",
        usage="<ticker>",
        extras={"category": "Watchlist"},
    )
    async def watched_ticker(self, ctx: commands.Context, ticker: str) -> None:
        target_ctx = await self._resolve_watch_context(ctx)
        await watch_list_manager.stop_watching(target_ctx, ticker)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WatchlistCog(bot))
