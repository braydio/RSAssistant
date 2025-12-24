"""Holdings refresh and audit commands."""

from __future__ import annotations

import asyncio
from datetime import datetime

import discord
from discord.ext import commands

from utils.channel_resolver import resolve_reply_channel
from utils.config_utils import DISCORD_PRIMARY_CHANNEL, HOLDINGS_LOG_CSV
from utils.csv_utils import clear_holdings_log
from utils.utility_utils import track_ticker_summary
from utils.on_message_utils import (
    REFRESH_WINDOW_DURATION,
    disable_audit,
    enable_audit,
    get_audit_summary,
    start_refresh_window,
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
            await ctx.send("!rsa holdings all")

            def check(message: discord.Message) -> bool:
                author_ok = message.author.bot or message.author.name.lower() == "auto-rsa"
                return (
                    message.channel == ctx.channel
                    and author_ok
                    and "All commands complete in all brokers" in message.content
                )

            try:
                await self.bot.wait_for("message", check=check, timeout=600)
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
        else:
            await ctx.send("Primary channel not found; unable to run holdings refresh.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HoldingsCog(bot))
