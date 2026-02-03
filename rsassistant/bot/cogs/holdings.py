"""Holdings refresh and audit commands."""

from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from rsassistant.bot.channel_resolver import resolve_reply_channel
from rsassistant.bot.history_query import show_sql_holdings_history
from utils.config_utils import DISCORD_HOLDINGS_CHANNEL, DISCORD_PRIMARY_CHANNEL, HOLDINGS_LOG_CSV
from utils.csv_utils import clear_holdings_log
from utils.holdings_snapshot import build_holdings_snapshot_embeds
from utils.utility_utils import track_ticker_summary
from rsassistant.bot.handlers.on_message import (
    REFRESH_WINDOW_DURATION,
    disable_audit,
    enable_audit,
    get_audit_summary,
    reset_holdings_completion_tracking,
    start_refresh_window,
    start_holdings_completion_tracking,
    wait_for_holdings_completion,
)
from utils.watch_utils import send_reminder_message_embed, watch_list_manager


class HoldingsCog(commands.Cog):
    """Commands for auditing holdings against the watchlist."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _clear_holdings_log(self, ctx: commands.Context) -> None:
        success, message = clear_holdings_log(HOLDINGS_LOG_CSV)
        await ctx.send(message if success else f"Failed to clear holdings log: {message}")

    @commands.command(
        name="clearholdings",
        aliases=["ch"],
        help="Clear entries in holdings_log.csv",
        extras={"category": "Admin"},
    )
    async def clear_holdings_command(self, ctx: commands.Context) -> None:
        await self._clear_holdings_log(ctx)

    @commands.command(
        name="all",
        help="Daily reminder with holdings refresh.",
        extras={"category": "Reporting"},
    )
    async def show_reminder(self, ctx: commands.Context) -> None:
        await ctx.send("Clearing the current holdings for refresh.")
        await self._clear_holdings_log(ctx)
        channel = resolve_reply_channel(self.bot, DISCORD_PRIMARY_CHANNEL)
        if channel:
            await send_reminder_message_embed(channel)
            enable_audit()
            start_refresh_window(self.bot, channel, REFRESH_WINDOW_DURATION)
            start_holdings_completion_tracking(self.bot)
            await ctx.send("!rsa holdings all")
            try:
                completed = await wait_for_holdings_completion(timeout=600)
                if not completed:
                    raise asyncio.TimeoutError
                summary = get_audit_summary()
                disable_audit()
                if summary:
                    embed = discord.Embed(
                        title="Missing Watchlist Holdings",
                        color=discord.Color.red(),
                    )
                    for account, tickers in summary.items():
                        embed.add_field(
                            name=account,
                            value=", ".join(tickers),
                            inline=False,
                        )
                    await ctx.send(embed=embed)
                watch_list = watch_list_manager.get_watch_list()
                results = []
                last_timestamp = ""
                for ticker in watch_list.keys():
                    statuses, ts = await track_ticker_summary(ctx, ticker, collect=True)
                    results.append((ticker, statuses))
                    last_timestamp = ts
                summary_embed = discord.Embed(
                    title="Broker Holdings Check", color=discord.Color.blue()
                )
                for ticker, statuses in results:
                    lines = [
                        f"{broker} {icon} {held}/{total}"
                        for broker, (icon, held, total) in statuses.items()
                    ]
                    summary_embed.add_field(
                        name=ticker, value="\n".join(lines) or "No data", inline=False
                    )
                if last_timestamp:
                    summary_embed.set_footer(text=f"Holdings snapshot • {last_timestamp}")
                await ctx.send(embed=summary_embed)
            except asyncio.TimeoutError:
                disable_audit()
                await ctx.send("Timed out waiting for AutoRSA response.")
            finally:
                reset_holdings_completion_tracking()
        else:
            await ctx.send("Primary channel not found; unable to run holdings refresh.")

    @commands.command(
        name="snapshot",
        aliases=["hs", "holdings"],
        help="Post a holdings snapshot to the holdings channel.",
        usage="[broker] [top_n]",
        extras={"category": "Reporting"},
    )
    async def holdings_snapshot(self, ctx: commands.Context, *args: str) -> None:
        broker = None
        top_n = 5
        if args:
            if len(args) == 1:
                if args[0].isdigit():
                    top_n = int(args[0])
                else:
                    broker = args[0]
            else:
                broker = args[0]
                if args[1].isdigit():
                    top_n = int(args[1])

        top_n = max(1, min(top_n, 10))
        channel = resolve_reply_channel(self.bot, DISCORD_HOLDINGS_CHANNEL) or ctx.channel

        embeds, error = build_holdings_snapshot_embeds(broker_filter=broker, top_n=top_n)
        if error:
            await ctx.send(error)
            return

        for embed in embeds:
            await channel.send(embed=embed)

        if channel.id != ctx.channel.id:
            await ctx.send(f"Holdings snapshot posted to {channel.mention}.")

    @commands.command(
        name="history",
        aliases=["hh"],
        help="Show historical holdings from the SQL log.",
        usage="[account] [ticker] [start_date] [end_date]",
        extras={"category": "Reporting"},
    )
    async def holdings_history(
        self,
        ctx: commands.Context,
        account: str | None = None,
        ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        """Display a holdings history plot based on optional filters."""

        await show_sql_holdings_history(
            ctx,
            account=account,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HoldingsCog(bot))
