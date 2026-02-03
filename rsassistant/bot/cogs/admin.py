"""Administrative commands."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
import subprocess

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

    @commands.command(
        name="patchautorsa",
        aliases=["patchrsa", "patch-auto-rsa"],
        help="Apply the auto-rsa holdings patch and set AUTO_RSA_HOLDINGS_FILE.",
        usage="<auto_rsa_dir> [holdings_file] [auto_rsa_env_file]",
        extras={"category": "Admin"},
    )
    async def patch_auto_rsa(
        self,
        ctx: commands.Context,
        auto_rsa_dir: str | None = None,
        holdings_file: str | None = None,
        auto_rsa_env_file: str | None = None,
    ) -> None:
        resolved_dir = auto_rsa_dir or os.getenv("AUTO_RSA_DIR")
        if not resolved_dir:
            await ctx.send(
                "Missing auto-rsa path. Provide it as the first argument or set AUTO_RSA_DIR."
            )
            return

        resolved_holdings = holdings_file or os.getenv("AUTO_RSA_HOLDINGS_FILE")
        if not resolved_holdings:
            await ctx.send(
                "Missing AUTO_RSA_HOLDINGS_FILE. Set it in config/.env or pass it as the second argument."
            )
            return

        resolved_env_file = auto_rsa_env_file or os.getenv("AUTO_RSA_ENV_FILE")
        script_path = Path(__file__).resolve().parents[3] / "scripts" / "apply-auto-rsa-patch.sh"

        if not script_path.exists():
            await ctx.send("Patcher script not found. Check scripts/apply-auto-rsa-patch.sh.")
            return

        env = os.environ.copy()
        env["AUTO_RSA_HOLDINGS_FILE"] = resolved_holdings
        if resolved_env_file:
            env["AUTO_RSA_ENV_FILE"] = resolved_env_file

        await ctx.send("Running auto-rsa patcher...")

        def _run_patcher():
            return subprocess.run(
                [str(script_path), resolved_dir],
                capture_output=True,
                text=True,
                env=env,
            )

        result = await asyncio.to_thread(_run_patcher)
        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip() or "(no output)"
        if len(output) > 1900:
            output = output[:1900] + "..."

        if result.returncode != 0:
            await ctx.send(f"Patcher failed:\n```{output}```")
            return

        await ctx.send(f"Patcher completed:\n```{output}```")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
