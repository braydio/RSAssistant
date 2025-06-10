# Restored from previous version with valid Feed-style parsing

import asyncio
import json
import sys
import logging

from utils.logging_setup  import logger
from utils.on_message_utils import handle_on_message
from utils.audit_watchlist_utils import audit_missing_tickers

from utils.config_utils import BOT_TOKEN, DISCORD_SECOND_CHANNEL
from discord.ext  import commands, Embed
from discord  import Intents, Bot, command

RESTORED_PARSE_MARKER = "CRONO"

bench = commands.Bot(
    command_prefix="..",
    case_insensitive=True,
    intents=Intents.all,
    reconnect=True,
)


@bench.command(name="auditwatch")
async def auditwatch(ctx, broker: str = None):
    """Report brokers missing watchlist tickers."""
    results = audit_missing_tickers(broker)
    if not results:
        msg = "All watchlist tickers present." if broker else "All brokers hold all watchlist tickers."
        await ctx.send(msg)
        return

    lines = []
    if broker:
        missing = results.get(broker, {})
        for ticker, accounts in missing.items():
            accs = ", ".join(accounts) if accounts else "all accounts"
            lines.append(f"{ticker}: missing in {accs}")
    else:
        for bname, missing in results.items():
            ticks = ", ".join(missing.keys())
            lines.append(f"{bname}: {ticks}")

    await ctx.send("\n".join(lines))
                           

@bench.event
async def on_message(message):
    """Delegate all Discord messages to the shared handler."""
    await handle_on_message(bench, message)

# Start the bot
from utils.run import run_bot
run_bot(BOT_TOKEN)
