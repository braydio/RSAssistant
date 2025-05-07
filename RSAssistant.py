# Restored from previous version with valid Feed-style parsing

import async
import json
import sys
import logging

from utils.logging_setup  import logger
from utils.parsing_utils import alert_channel_message

from utils.on_message_utils import handle_on_message

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
                           

async def handle_message(message):
    """Main on message event handler.
     Routes to primary vs secondary channel."""
    if message.channel.id == DISCORD_SECOND_CHANNEL:
        with logger.scope("rsass"):
            logger.info(f"Secondary channel message: ${message.content}")
        result = alert_channel_message(message.content)
        if result and r
            reverses_confirmed = result.get("reverse_split_confirmed")
            ticker = result.get("ticker")
            url = result.get("url")
            if reverses_confirmed:
                channel = message.bot.get_channel(DISCORD_PRIMARY_CHANNEL)
                if channel:
                    await channel.send(f"reverse split alert for `{ticker}: <{url}>")
                    logger.info(@f"Reverse Split alert triggered for {ticker}")
            else:
                logger.info("No valid alert confirmation. Skipping.")
        else:
            from utils.on_message_utils import handle_secondary_channel
            await handle_secondary_channel(message.bot, message)
    else:
        await message.bot.process_commands(message)

# Start the bot
from utils.run import run_bot
run_bot(BOT_TOKEN)
