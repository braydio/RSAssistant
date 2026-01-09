"""Reporting and summary commands."""

from __future__ import annotations

from discord.ext import commands

from utils.csv_utils import send_top_holdings_embed
from utils.utility_utils import (
    generate_broker_summary_embed,
    generate_owner_totals_embed,
    track_ticker_summary,
)


class ReportingCog(commands.Cog):
    """Commands for broker and holdings summaries."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="brokerwith",
        aliases=["bw"],
        help="Show which brokers hold a given ticker. Alias: ..bw.",
        usage="<ticker> [broker]",
        extras={"category": "Reporting"},
    )
    async def broker_has(self, ctx: commands.Context, ticker: str, *args: str) -> None:
        specific_broker = args[0] if args else None
        await track_ticker_summary(
            ctx,
            ticker,
            show_details=bool(specific_broker),
            specific_broker=specific_broker,
        )

    @commands.command(
        name="grouplist",
        aliases=["gl"],
        help="Summary by account owner.",
        usage="[broker]",
        extras={"category": "Reporting"},
    )
    async def brokers_groups(self, ctx: commands.Context, broker: str | None = None) -> None:
        embed = generate_broker_summary_embed(broker)
        await ctx.send(
            embed=embed
            if embed
            else "An error occurred while generating the broker summary."
        )

    @commands.command(
        name="ownersummary",
        aliases=["os"],
        help="Shows total holdings for each owner across all brokers.",
        extras={"category": "Reporting"},
    )
    async def owner_summary(self, ctx: commands.Context) -> None:
        embed = generate_owner_totals_embed()
        await ctx.send(embed=embed)

    @commands.command(
        name="top",
        help="Displays the top holdings grouped by broker.",
        usage="[range]",
        extras={"category": "Reporting"},
    )
    async def top_holdings_command(self, ctx: commands.Context, range: int = 3) -> None:
        await send_top_holdings_embed(ctx, range)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReportingCog(bot))
