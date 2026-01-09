"""Administrative commands."""

from __future__ import annotations

import asyncio
import os
import sys

from discord.ext import commands


class AdminCog(commands.Cog):
    """Commands restricted to bot admins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="restart", aliases=["rs"], extras={"category": "Admin"})
    async def restart(self, ctx: commands.Context) -> None:
        await ctx.send("\n(・_・ヾ)     (-.-)Zzz...\n")
        await ctx.send(
            "AYO WISEGUY THIS COMMAND IS BROKEN AND WILL BE DISRUPTIVE TO THE DISCORD BOT! NICE WORK GENIUS!"
        )
        await asyncio.sleep(1)
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception as exc:
            await ctx.send("An error occurred while attempting to restart the bot.")
            return

    @commands.command(
        name="clear",
        aliases=["clr"],
        help="Batch clears excess messages.",
        usage="<limit>",
        extras={"category": "Admin"},
    )
    @commands.has_permissions(manage_messages=True)
    async def batchclear(self, ctx: commands.Context, limit: int) -> None:
        if limit > 10000:
            await ctx.send("That's too many brother man.")

        messages_deleted = 0
        while limit > 0:
            batch_size = min(limit, 100)
            deleted = await ctx.channel.purge(limit=batch_size)
            messages_deleted += len(deleted)
            limit -= batch_size
            await asyncio.sleep(0.1)

        await ctx.send(f"Deleted {limit} messages", delete_after=5)

    @commands.command(
        name="shutdown",
        aliases=["sd"],
        help="Gracefully shuts down the bot.",
        extras={"category": "Admin"},
    )
    async def shutdown(self, ctx: commands.Context) -> None:
        await ctx.send("no you")
        await self.bot.close()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
