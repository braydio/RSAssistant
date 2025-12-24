"""Account mapping and broker listing commands."""

from __future__ import annotations

from discord.ext import commands

from utils.excel_utils import (
    add_account_mappings,
    clear_account_mappings,
    index_account_details,
    map_accounts_in_excel_log,
)
from utils.utility_utils import all_account_nicknames, all_brokers


class AccountsCog(commands.Cog):
    """Commands for account mappings and broker listings."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="brokerlist",
        help="List all active brokers or accounts for a broker.",
        usage="[broker]",
        extras={"category": "Accounts"},
    )
    async def brokerlist(self, ctx: commands.Context, broker: str | None = None) -> None:
        if broker is None:
            await all_brokers(ctx)
        else:
            await all_account_nicknames(ctx, broker)

    @commands.command(
        name="addmap",
        help="Add account mapping details.",
        usage="<brokerage> <broker_no> <account> <nickname>",
        extras={"category": "Accounts"},
    )
    async def add_account_mappings_command(
        self, ctx: commands.Context, brokerage: str, broker_no: str, account: str, nickname: str
    ) -> None:
        if not (brokerage and broker_no and account and nickname):
            await ctx.send(
                "All arguments are required: `<brokerage> <broker_no> <account> <nickname>`."
            )
            return
        await add_account_mappings(ctx, brokerage, broker_no, account, nickname)

    @commands.command(
        name="loadmap",
        help="Map account details from Excel to JSON.",
        extras={"category": "Accounts"},
    )
    async def load_account_mappings_command(self, ctx: commands.Context) -> None:
        await ctx.send("Mapping account details...")
        await index_account_details(ctx)
        await ctx.send(
            "Mapping complete.\n Run `..loadlog` to save mapped accounts to the excel logger."
        )

    @commands.command(
        name="loadlog",
        help="Update Excel log with mapped accounts.",
        extras={"category": "Accounts"},
    )
    async def update_log_with_mappings(self, ctx: commands.Context) -> None:
        await ctx.send("Updating log with mapped accounts...")
        await map_accounts_in_excel_log(ctx)
        await ctx.send("Complete.")

    @commands.command(
        name="clearmap",
        help="Remove all saved account mappings.",
        extras={"category": "Accounts"},
    )
    async def clear_mapping_command(self, ctx: commands.Context) -> None:
        await ctx.send("Clearing account mappings...")
        await clear_account_mappings(ctx)
        await ctx.send("Account mappings have been cleared.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AccountsCog(bot))
