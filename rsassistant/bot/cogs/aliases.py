"""Command alias listing helpers."""

from __future__ import annotations

from collections import defaultdict

from discord.ext import commands

from utils.config_utils import BOT_PREFIX


class AliasesCog(commands.Cog):
    """Commands for listing configured aliases."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="aliases",
        help="List command aliases.",
        extras={"category": "Help"},
    )
    async def show_aliases(self, ctx: commands.Context) -> None:
        prefix = (getattr(ctx, "prefix", None) or BOT_PREFIX).strip()
        aliases_by_cog: dict[str, list[tuple[str, str]]] = defaultdict(list)

        for command in self.bot.commands:
            if command.name == "aliases" or not command.aliases:
                continue
            cog_name = command.cog_name or "Other"
            alias_list = ", ".join(f"{prefix}{alias}" for alias in command.aliases)
            aliases_by_cog[cog_name].append((command.name, alias_list))

        if not aliases_by_cog:
            await ctx.send("No aliases are currently configured.")
            return

        lines = ["**Aliases**"]
        for cog_name in sorted(aliases_by_cog):
            lines.append(f"{cog_name}:")
            for command_name, alias_list in sorted(aliases_by_cog[cog_name]):
                lines.append(f"{prefix}{command_name} -> {alias_list}")

        await ctx.send("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AliasesCog(bot))
