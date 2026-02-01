"""Account mapping and broker listing commands."""

from __future__ import annotations

from discord.ext import commands

from utils.config_utils import load_account_mappings, save_account_mappings
from utils.sql_utils import (
    clear_account_nicknames,
    sync_account_mappings,
    upsert_account_mapping,
)
from utils.utility_utils import all_account_nicknames, all_brokers


class AccountsCog(commands.Cog):
    """Commands for account mappings and broker listings."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="brokerlist",
        aliases=["bl"],
        help="List all active brokers or accounts for a broker.",
        usage="[broker]",
        extras={"category": "Accounts"},
    )
    async def brokerlist(
        self, ctx: commands.Context, broker: str | None = None
    ) -> None:
        if broker is None:
            await all_brokers(ctx)
        else:
            await all_account_nicknames(ctx, broker)

    @commands.command(
        name="addmap",
        aliases=["am"],
        help="Add account mapping details.",
        usage="<brokerage> <broker_no> <account> <nickname>",
        extras={"category": "Accounts"},
    )
    async def add_account_mappings_command(
        self,
        ctx: commands.Context,
        brokerage: str,
        broker_no: str,
        account: str,
        nickname: str,
    ) -> None:
        """Add or update an account mapping in JSON and SQL storage."""
        if not (brokerage and broker_no and account and nickname):
            await ctx.send(
                "All arguments are required: `<brokerage> <broker_no> <account> <nickname>`."
            )
            return
        mappings = load_account_mappings()
        mappings.setdefault(brokerage, {}).setdefault(broker_no, {})[account] = nickname
        save_account_mappings(mappings)
        upsert_account_mapping(brokerage, broker_no, account, nickname)
        await ctx.send(
            f"Added mapping: {brokerage} - Broker No: {broker_no}, Account: {account}, Nickname: {nickname}"
        )

    @commands.command(
        name="loadmap",
        aliases=["lm"],
        help="Sync account mappings from JSON into SQL storage.",
        extras={"category": "Accounts"},
    )
    async def load_account_mappings_command(self, ctx: commands.Context) -> None:
        """Sync account mappings from JSON into SQL storage."""
        await ctx.send("Syncing account mappings to SQL...")
        mappings = load_account_mappings()
        if not mappings:
            await ctx.send("No account mappings found to sync.")
            return
        results = sync_account_mappings(mappings)
        await ctx.send(
            "Account mapping sync complete."
            f" Added: {results['added']}, Updated: {results['updated']}."
        )

    @commands.command(
        name="loadlog",
        aliases=["ll"],
        help="Refresh SQL account mapping storage from JSON.",
        extras={"category": "Accounts"},
    )
    async def update_log_with_mappings(self, ctx: commands.Context) -> None:
        """Refresh SQL account mappings from JSON storage."""
        await ctx.send("Refreshing SQL account mappings from JSON...")
        mappings = load_account_mappings()
        if not mappings:
            await ctx.send("No account mappings found to sync.")
            return
        results = sync_account_mappings(mappings)
        await ctx.send(
            "Account mapping refresh complete."
            f" Added: {results['added']}, Updated: {results['updated']}."
        )

    @commands.command(
        name="clearmap",
        aliases=["cm"],
        help="Remove all saved account mappings.",
        extras={"category": "Accounts"},
    )
    async def clear_mapping_command(self, ctx: commands.Context) -> None:
        """Clear account mapping data from JSON and SQL storage."""
        await ctx.send("Clearing account mappings...")
        save_account_mappings({})
        cleared = clear_account_nicknames()
        await ctx.send(f"Account mappings have been cleared. ({cleared} SQL rows)")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AccountsCog(bot))
