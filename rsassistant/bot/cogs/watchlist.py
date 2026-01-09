"""Watchlist management commands."""

from __future__ import annotations

from discord.ext import commands

from utils.watch_utils import watch as handle_watch_command
from utils.watch_utils import watch_list_manager


class WatchlistCog(commands.Cog):
    """Commands for managing watchlist entries and split ratios."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="watch",
        aliases=["wa"],
        help="Add ticker(s) to the watchlist.",
        usage="<ticker> <split_date> [split_ratio] | <ticker ratio (purchase by mm/dd)>",
        extras={"category": "Watchlist"},
    )
    async def watch(self, ctx: commands.Context, *, text: str) -> None:
        await handle_watch_command(ctx, text=text)

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
        await watch_list_manager.watch_ratio(ctx, ticker, split_ratio)

    @commands.command(
        name="watchlist",
        aliases=["wl"],
        help="List all tickers currently being watched.",
        extras={"category": "Watchlist"},
    )
    async def all_watching(self, ctx: commands.Context) -> None:
        await watch_list_manager.list_watched_tickers(ctx, include_prices=True)

    @commands.command(
        name="watched",
        aliases=["ok", "wd"],
        help="Remove a ticker from the watchlist.",
        usage="<ticker>",
        extras={"category": "Watchlist"},
    )
    async def watched_ticker(self, ctx: commands.Context, ticker: str) -> None:
        await watch_list_manager.stop_watching(ctx, ticker)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WatchlistCog(bot))
