"""Account mapping and broker listing commands."""

from __future__ import annotations

from discord.ext import commands

from utils.sql_utils import (
    clear_account_nicknames,
    migrate_legacy_json_data,
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
        """Add or update an account mapping in SQL storage."""
        if not (brokerage and broker_no and account and nickname):
            await ctx.send(
                "All arguments are required: `<brokerage> <broker_no> <account> <nickname>`."
            )
            return
        upsert_account_mapping(brokerage, broker_no, account, nickname)
        await ctx.send(
            f"Added mapping: {brokerage} - Broker No: {broker_no}, Account: {account}, Nickname: {nickname}"
        )

    @commands.command(
        name="loadmap",
        aliases=["lm"],
        help="Migrate legacy JSON data into SQL storage.",
        extras={"category": "Accounts"},
    )
    async def load_account_mappings_command(self, ctx: commands.Context) -> None:
        """Migrate legacy JSON account mappings into SQL storage."""
        await ctx.send(
            "Migrating legacy JSON data (mappings/watchlist/sell list) to SQL..."
        )
        results = migrate_legacy_json_data()
        await ctx.send(
            "Migration complete."
            f" account_mappings={results['account_mappings']} watchlist={results['watchlist']} sell_list={results['sell_list']}."
        )

    @commands.command(
        name="loadlog",
        aliases=["ll"],
        help="Re-run legacy JSON migration into SQL storage.",
        extras={"category": "Accounts"},
    )
    async def update_log_with_mappings(self, ctx: commands.Context) -> None:
        """Re-run the legacy JSON migration for account mappings."""
        await ctx.send("Re-running legacy JSON migration...")
        results = migrate_legacy_json_data()
        await ctx.send(
            "Migration refresh complete."
            f" account_mappings={results['account_mappings']} watchlist={results['watchlist']} sell_list={results['sell_list']}."
        )

    @commands.command(
        name="clearmap",
        aliases=["cm"],
        help="Remove all saved account mappings.",
        extras={"category": "Accounts"},
    )
    async def clear_mapping_command(self, ctx: commands.Context) -> None:
        """Clear account mapping data from SQL storage."""
        await ctx.send("Clearing account mappings...")
        cleared = clear_account_nicknames()
        await ctx.send(f"Account mappings have been cleared. ({cleared} SQL rows)")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AccountsCog(bot))
