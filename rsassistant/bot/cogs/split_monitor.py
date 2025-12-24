"""Reverse split monitoring commands."""

from __future__ import annotations

import datetime

from discord.ext import commands

from utils import split_watch_utils


class SplitMonitorCog(commands.Cog):
    """Commands for tracking reverse-split watch entries."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="splitwatch",
        help="Add a ticker to the reverse-split watchlist.",
        usage="<ticker> <yyyy-mm-dd>",
        extras={"category": "Split Monitor"},
    )
    async def add_split_watch(self, ctx: commands.Context, ticker: str, split_date: str) -> None:
        try:
            datetime.datetime.strptime(split_date, "%Y-%m-%d")
        except ValueError:
            await ctx.send("Invalid date format. Please use YYYY-MM-DD.")
            return

        split_watch_utils.add_split_watch(ticker, split_date)
        await ctx.send(f"Tracking {ticker.upper()} for reverse split on {split_date}.")

    @commands.command(
        name="splitstatus",
        help="Show reverse-split progress for a ticker.",
        usage="<ticker>",
        extras={"category": "Split Monitor"},
    )
    async def split_status(self, ctx: commands.Context, ticker: str) -> None:
        status = split_watch_utils.get_status(ticker)
        if not status:
            await ctx.send(f"{ticker.upper()} is not being tracked.")
            return

        bought = ", ".join(status.get("accounts_bought", [])) or "None"
        sold = ", ".join(status.get("accounts_sold", [])) or "None"
        await ctx.send(
            f"{ticker.upper()} | Split: {status.get('split_date')} | Phase: {status.get('status')}\n"
            f"Bought: {bought}\nSold: {sold}"
        )

    @commands.command(
        name="splitlist",
        help="List tickers under reverse-split monitoring.",
        extras={"category": "Split Monitor"},
    )
    async def split_list(self, ctx: commands.Context) -> None:
        watchlist = split_watch_utils.get_full_watchlist()
        if not watchlist:
            await ctx.send("No reverse splits are currently being monitored.")
            return

        lines = []
        for ticker, info in watchlist.items():
            lines.append(
                f"{ticker}: {info.get('split_date')} ({info.get('status', 'unknown')})"
            )
        await ctx.send("\n".join(lines))

    @commands.command(
        name="splitcleanup",
        help="Advance phases and remove completed reverse splits.",
        extras={"category": "Split Monitor"},
    )
    async def split_cleanup(self, ctx: commands.Context) -> None:
        split_watch_utils.update_split_status()
        split_watch_utils.cleanup_completed_tickers()
        await ctx.send("Updated reverse split statuses and cleaned completed entries.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SplitMonitorCog(bot))
