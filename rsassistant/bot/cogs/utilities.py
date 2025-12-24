"""Utility commands for RSAssistant."""

from __future__ import annotations

from discord.ext import commands

from utils.utility_utils import print_to_discord


class UtilitiesCog(commands.Cog):
    """Commands for utility tasks."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="todiscord",
        help="Print a text file to Discord one line at a time.",
        extras={"category": "Utilities"},
    )
    async def print_by_line(self, ctx: commands.Context) -> None:
        await print_to_discord(ctx)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilitiesCog(bot))
