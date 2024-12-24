import asyncio
import json
import logging
import os
import sys
import signal
import shutil
import time
from datetime import datetime


# Third-party imports
import discord
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord import Embed
from discord.ext import commands

# Local utility imports
from utils.webdrive_utils import StockSplitScraper, stock_splits
from utils.excel_utils import (clear_account_mappings, index_account_details,
                               map_accounts_in_excel_log)
from utils.parsing_utils import (parse_embed_message, alert_channel_message,
                                 parse_manual_order_message,
                                 parse_order_message)
from utils.sql_utils import get_db_connection, init_db
from utils.csv_utils import clear_holdings_log, send_top_holdings_embed
from utils.utility_utils import (all_account_nicknames, all_brokers,
                                 generate_broker_summary_embed,
                                 print_to_discord, track_ticker_summary,
                                 update_file_version, get_file_version)
from utils.watch_utils import (list_watched_tickers,
                               periodic_check, send_reminder_message_embed,
                               stop_watching, watch_ratio, watch_ticker)
from utils.init import (FILE_VERSION, APP_NAME, RUNTIME_ENVIRONMENT,
                        ACCOUNT_MAPPING_FILE, HOLDINGS_LOG_CSV,
                        EXCEL_FILE_MAIN_PATH, CONFIG_PATH, BOT_TOKEN,
                        DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL,                      
                        config, load_account_mappings, setup_logging)

RUNTIME_UPPER = RUNTIME_ENVIRONMENT.capitalize()
bot_info = (f'{APP_NAME} - v{FILE_VERSION} by @braydio \n    <https://github.com/braydio/RSAssistant> \n \n ')

# Load configuration and logging
setup_logging(config)
init_db()

account_mapping = load_account_mappings
CONFIG_TOKEN = config["discord"]["token"]
CONFIG_CHANNEL = config["discord_ids"]['channel_id']
CONFIG_CHANNEL2 = config["discord_ids"]['channel_id2']


# Chapt Environment variables
critical_env = "Terminating startup. Missing critical environment variable: "
BOT_TOKEN = os.getenv("BOT_TOKEN", CONFIG_TOKEN)
if not BOT_TOKEN:
    logging.error(f"{critical_env} BOT_TOKEN")
    sys.exit(f"{critical_env} BOT_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", CONFIG_CHANNEL))
ALERTS_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID2", CONFIG_CHANNEL2))

logging.info(f"Target channel {TARGET_CHANNEL_ID}")
# Set up bot intents
intents = discord.Intents.default()
intents.message_content = config["discord"]["intents"]["message_content"]
intents.guilds = config["discord"]["intents"]["guilds"]
intents.members = config["discord"]["intents"]["members"]


# Initialize bot
bot = commands.Bot(
    command_prefix=config["discord"]["prefix"], case_insensitive=True, intents=intents
)

global periodic_task, reminder_scheduler


@bot.command(name="shutdown", help="Shuts down the bot.")
async def shutdown(ctx):
    await ctx.send("no you")
    logging.info("Shutdown from main. Deactivating.")
    shutdown_handler(signal.SIGTERM, None)  # Manually call the handler

# Graceful shutdown handler
def shutdown_handler(signal_received, frame):
    logging.info("RSAssistant - shutting down...")
    global periodic_check, reminder_scheduler
    if periodic_check and not periodic_check.done():
        periodic_check.cancel()
    if reminder_scheduler:
        reminder_scheduler.shutdown()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

async def send_negative_holdings(quantity, stock, alert_type, broker_name, broker_number, account_number):
    """
    Sends an alert message to the target Discord channel for negative holdings.

    Args:
        quantity (float): The negative quantity detected.
        stock (str): The stock symbol associated with the alert.
        alert_type (str): Type of alert, e.g., "Negative Holdings".
        broker_name (str): The name of the broker.
        broker_number (str): The broker's identifier.
        account_number (str): The account number associated with the holdings.

    Raises:
        Exception: If the channel cannot be found or an error occurs while sending the message.
    """
    try:
        # Fetch the target channel
        channel = bot.get_channel(TARGET_CHANNEL_ID)

        if channel:
            # Build the embed message
            embed = Embed(
                title=f"Alert! {alert_type}",
                description="A negative holdings quantity was detected.",
                color=0xFF0000,
            )
            embed.add_field(name="Stock", value=stock, inline=True)
            embed.add_field(name="Quantity", value=quantity, inline=True)
            embed.add_field(name="Broker Name", value=broker_name, inline=True)
            embed.add_field(name="Broker Number", value=broker_number, inline=True)
            embed.add_field(name="Account Number", value=account_number, inline=True)

            # Send the message
            await channel.send(embed=embed)
            logging.info(f"Negative holdings alert sent for stock {stock}.")
        else:
            logging.error(f"Target channel with ID {TARGET_CHANNEL_ID} not found.")

    except Exception as e:
        logging.error(f"Error sending negative holdings alert: {e}")


# Start the bot with the token from the .env
if __name__ == "__main__":
    bot.run(BOT_TOKEN)