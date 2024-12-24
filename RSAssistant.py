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
from utils.webdrive_utils import StockSplitScraper
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

@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    
    await asyncio.sleep(2)
    logging.info(f"{APP_NAME} by @braydio - GitHub: https://github.com/braydio/RSAssistant")
    logging.info(f"Version {FILE_VERSION} | Runtime Environment: {RUNTIME_UPPER}")
    await asyncio.sleep(3)
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    
    account_setup_message = f"\n\n**(╯°□°）╯**\n\n Account mappings not found. Please fill in Reverse Split Log > Account Details sheet at\n`{EXCEL_FILE_MAIN_PATH}`\n\nThen run: `..loadmap` and `..loadlog`."
    
    try:
        with open(ACCOUNT_MAPPING_FILE, "r") as file:
            account_mappings = json.load(file)
        ready_message = (
            account_setup_message
            if not account_mappings
            else "...watching for order activity...\n(✪‿✪)"
        )
    except (FileNotFoundError, json.JSONDecodeError):
        ready_message = account_setup_message
        
    if channel:
        await channel.send(ready_message)
    else:
        logging.warning(f"Target Channel not found - ID: {TARGET_CHANNEL_ID} on startup.")

    logging.info(f"Initializing Application in {RUNTIME_ENVIRONMENT} environment.")
    logging.info(f"{bot.user} has connected to Discord!")

    # Start periodic check task if not already running
    if 'periodic_task' not in globals() or periodic_task is None:
        periodic_task = asyncio.create_task(periodic_check(bot))
        logging.info("Periodic task started.")
    else:
        logging.info("Periodic task already running.")

    # Schedule reminder task using APScheduler
    if 'reminder_scheduler' not in globals() or reminder_scheduler is None:
        reminder_scheduler = BackgroundScheduler()
        reminder_scheduler.add_job(lambda: bot.loop.create_task(send_reminder_message_embed(bot)), CronTrigger(hour=8, minute=45))
        reminder_scheduler.add_job(lambda: bot.loop.create_task(send_reminder_message_embed(bot)), CronTrigger(hour=15, minute=30))
        reminder_scheduler.start()
        logging.info("Scheduled reminders at 8:45 AM and 3:30 PM started.")
    else:
        logging.info("Reminder scheduler already running.")
    category = "Startup and Shutdown"

@bot.command(name="version", help="Displays the current app version.")
async def version(ctx):
    embed_version = discord.Embed(
        color=discord.Color.green()
        )
    embed_version.add_field(
        name=f"{APP_NAME} - Version Details: ",
        value=bot_info
    )
    await ctx.send(embed=embed_version)
    # await ctx.send(f"{APP_NAME} - Version: {FILE_VERSION}")

@bot.command(name="restart")
async def restart(ctx):
    """Restarts the bot."""
    await ctx.send("\n(・_・ヾ)     (-.-)Zzz...\nAYO WISEGUY THIS COMMAND IS BROKEN AND WILL BE DISRUPTIVE TO THE DISCORD BOT\nNICE WORK GENIUS")
    await asyncio.sleep(1)
    logging.info("Attempting to restart the bot...")
    try:
        python = sys.executable
        os.execv(python, [python] + sys.argv)
    except Exception as e:
        logging.error(f"Error during restart: {e}")
        await ctx.send("An error occurred while attempting to restart the bot.")

@bot.event
async def on_message(message):
    """Triggered when a message is received in the target channel."""
    if message.author == bot.user:
        return  # Prevents the bot from responding to itself

    # Check if the message was sent in the target channel
    if message.channel.id == TARGET_CHANNEL_ID:

        if message.content.lower().startswith("manual"):
            parse_manual_order_message(message.content)
        elif message.embeds:
            parse_embed_message(message.embeds[0])
        else:
            parse_order_message(message.content)
    
    if message.channel.id == ALERTS_CHANNEL_ID:
        if message.content:
            logging.info(f"Received message: {message.content}")
            
            channel = bot.get_channel(TARGET_CHANNEL_ID)
            parsed_message = alert_channel_message(message.content)

            if parsed_message:
                await channel.send(f"\n{parsed_message}")
                logging.info("Alert sent successfully.")
            else:
                logging.warning("Parsed message is None. No alert sent.")

            # Optional notification
            # await channel.send("Nasdaq Corporate Actions Alert: See channel #reverse-splits")


    # Pass the message to the command processing so bot commands work
    await bot.process_commands(message)

async def send_buy(ctx):
    order_details = "!ping"
    # "!rsa buy 1 slxn chase"
    await ctx.send(order_details)

@bot.command(name="websearch", help="Surfin' the web!")
async def splits_search(ctx, mode: str, ticker: str = None):
    scraper = StockSplitScraper()
    await scraper.run(ctx, mode, ticker)

@bot.command(name="reminder", help="Shows daily reminder")
async def show_reminder(ctx):
    """Shows a daily reminder message."""
    await send_reminder_message_embed(ctx)

async def send_scheduled_reminder():
    """Send scheduled reminders to the target channel."""
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel:
        await send_reminder_message_embed(channel)
    else:
        logging.error(f"Could not find channel with ID: {TARGET_CHANNEL_ID} to send reminder.")


@bot.command(name="brokerlist", help="List all active brokers. Optional arg: Broker")
async def brokerlist(ctx, broker: str = None):
    """Lists all brokers or accounts for a specific broker."""
    try:
        if broker is None:
            await all_brokers(ctx)
        else:
            await all_account_nicknames(ctx, broker)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")


@bot.command(name="brokerwith", help="All brokers with specified tickers > brokerwith <ticker> (details)",)
async def broker_has(ctx, ticker: str, *args):
    """Shows broker-level summary for a specific ticker."""
    specific_broker = args[0] if args else None
    await track_ticker_summary(
        ctx, ticker, show_details=bool(specific_broker), specific_broker=specific_broker
    )


@bot.command(name="grouplist", help="Summary by account owner. Optional: specify a broker.")
async def brokers_groups(ctx, broker: str = None):
    """
    Displays account owner summary for a specific broker or all brokers if no broker is specified.
    """
    embed = generate_broker_summary_embed(ctx, broker)
    await ctx.send(
        embed=(
            embed if embed else "An error occurred while generating the broker summary."
        )
    )


# Discord bot command
@bot.command(name="top",
    help="Displays the top holdings by dollar value (Quantity <= 1) grouped by broker.")
async def top_holdings_command(ctx, range: int = 3):
    """
    Discord bot command to show top holdings by broker level.

    Args:
        ctx: Discord context object.
        range (int): Number of top holdings to display per broker.
    """
    try:
        # Send the embed message
        await send_top_holdings_embed(ctx, range)

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")



@bot.command(name="watch",
    help="Add ticker to watchlist. Args: split_date split_ratio format: 'mm/dd' 'r-r'",
)
async def watch(ctx, ticker: str, split_date: str = None, split_ratio: str = None):
    """Adds a ticker to the watchlist with an optional split date and split ratio."""
    try:
        if split_date:
            datetime.strptime(split_date, "%m/%d")  # Validates the format as mm/dd
    except ValueError:
        await ctx.send("Invalid date format. Please use * mm/dd * e.g., 11/4.")
        return

    if not split_date:
        await ctx.send("Please include split date: * mm/dd *")
        return

    if split_ratio and not split_ratio.count("-") == 1:
        await ctx.send("Invalid split ratio format. Use 'X-Y' format (e.g., 1-10).")
        return

    await watch_ticker(ctx, ticker, split_date, split_ratio)


@bot.command(name="addratio",
    help="Adds or updates the split ratio for an existing ticker in the watchlist.",
)
async def add_ratio(ctx, ticker: str, split_ratio: str):

    if not split_ratio:
        await ctx.send("Please include split ratio: * X-Y *")
        return

    await watch_ratio(ctx, ticker, split_ratio)


@bot.command(name="watchlist",
    help="Lists all tickers currently being watched.")
async def allwatching(ctx):
    """Lists all tickers being watched."""
    await list_watched_tickers(ctx)


@bot.command(name="watched", help="Removes a ticker from the watchlist.")
async def watched_ticker(ctx, ticker: str):
    """Removes a ticker from the watchlist."""
    await stop_watching(ctx, ticker)


@bot.command(name="todiscord", help="Prints text file one line at a time")
async def print_by_line(ctx):
    """Prints contents of a file to Discord, one line at a time."""
    await print_to_discord(ctx)


@bot.command(name="loadmap", help="Maps accounts from Account Details excel sheet")
async def load_account_mappings_command(ctx):
    """Maps account details from the Excel sheet to JSON."""
    try:
        await ctx.send("Mapping account details...")
        await index_account_details(ctx)
        await ctx.send(
            "Mapping complete.\n Run `..loadlog` to save mapped accounts to the excel logger."
        )
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")


@bot.command(name="loadlog", help="Updates excel log with mapped accounts")
async def update_log_with_mappings(ctx):
    """Updates the Excel log with mapped accounts."""
    try:
        await ctx.send("Updating log with mapped accounts...")
        await map_accounts_in_excel_log(ctx)
        await ctx.send("Complete.")
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")


@bot.command(name="clearmap", help="Clears all account mappings from the account_mapping.json file",)
async def clear_mapping_command(ctx):
    """Clears all account mappings from the JSON file."""
    try:
        await ctx.send("Clearing account mappings...")
        await clear_account_mappings(ctx)
        await ctx.send("Account mappings have been cleared.")
    except Exception as e:
        await ctx.send(f"An error occurred during the clearing process: {str(e)}")

@bot.command(name="clearholdings", help="Clears entries in holdings_log.csv")
async def clear_holdings(ctx):
    """Clears all holdings from the CSV file."""
    success, message = clear_holdings_log(HOLDINGS_LOG_CSV)
    await ctx.send(message if success else f"Failed to clear holdings log: {message}")

@bot.command(name="updateconfig", help="Dev tool to get or update file version.")
async def update_version(ctx, version: str = None):
    """
    Gets or updates the file version in the configuration.
    
    Args:
        ctx: Discord context.
        version (str): Optional. If provided, updates the file version. If not, retrieves the current file version.
    """
    try:
        if version:
            # Update the file version if a new version is provided
            success = update_file_version(config_path=CONFIG_PATH, version=version)
            if success:
                await ctx.send(f"Configuration updated successfully to version {version}.")
            else:
                await ctx.send(f"Failed to update configuration.")
        else:
            # Fetch the current file version if no version is provided
            file_version = get_file_version(config_path=CONFIG_PATH)
            if file_version:
                await ctx.send(f"Current file version: {file_version}")
            else:
                await ctx.send(f"Failed to fetch the current file version.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

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