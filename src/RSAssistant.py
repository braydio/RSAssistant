import asyncio
import json
import logging
import os
import sys
import signal
from datetime import datetime

# Third-party imports
import discord
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord import Embed
from discord.ext import commands
from dotenv import load_dotenv

# Local utility imports
from utils.excel_utils import (clear_account_mappings, index_account_details,
                               map_accounts_in_excel_log)
from utils.parsing_utils import (parse_embed_message,
                                 parse_manual_order_message,
                                 parse_order_message)
from utils.sql_utils import get_db_connection, init_db
from utils.csv_utils import clear_holdings_log
from utils.utility_utils import (all_account_nicknames, all_brokers,
                                 generate_broker_summary_embed,
                                 print_to_discord, track_ticker_summary,
                                 update_file_version, get_file_version)
from utils.watch_utils import (list_watched_tickers, load_watch_list,
                               periodic_check, send_reminder_message_embed,
                               stop_watching, watch_ratio, watch_ticker)
from utils.init import (FILE_VERSION, APP_NAME, FILE_ENVIRONMENT,
                        ACCOUNT_MAPPING_FILE, HOLDINGS_LOG_CSV,
                        EXCEL_FILE_MAIN_PATH, CONFIG_PATH, DOTENV_PATH,                       
                        load_config, load_account_mappings, setup_logging)

startup_banner = (
r"""
   ___  _______           _     __            __ 
  / _ \/ __/ _ | ___ ___ (_)__ / /____ ____  / /_
 / , _/\ \/ __ |(_-<(_-</ (_-</ __/ _ `/ _ \/ __/
/_/|_/___/_/ |_/___/___/_/___/\__/\_,_/_//_/\__/   
""")

tagline = (f'{APP_NAME} - v{FILE_VERSION} by @braydio \n    <https://github.com/braydio/RSAssistant> \n \n ')

# Initialize env, config, logging
load_dotenv()
config = load_config()
setup_logging()


# Validate paths in the configuration
def validate_paths():
    missing_paths = []
    for key, path in config["paths"].items():
        if not os.path.exists(path):
            missing_paths.append((key, path))
            logging.warning(f"Path not found: {key} -> {path}")
    return missing_paths

missing_paths = validate_paths()
if missing_paths:
    logging.error(f"Missing paths detected: {missing_paths}")

if config["environment"]["mode"] == "development":
    logging.getLogger().setLevel(logging.DEBUG)

# Extract shortcuts and prefix
shortcuts = config.get("shortcuts", {})
prefix = config["discord"]["prefix"]
task = None

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = config["discord"]["intents"]["message_content"]
intents.guilds = config["discord"]["intents"]["guilds"]
intents.members = config["discord"]["intents"]["members"]

# Initialize bot
bot = commands.Bot(
    command_prefix=config["discord"]["prefix"], case_insensitive=True, intents=intents
)

load_dotenv(DOTENV_PATH)

def validate_env_vars():
    """
    Validates the presence of critical environment variables required for the application.
    Logs errors and exits the program if any required variables are missing.
    
    Returns:
        dict: A dictionary of the validated environment variables and their values.
    """
    # Define required environment variables with defaults (None if required)
    required_vars = {
        "BOT_TOKEN": os.getenv("BOT_TOKEN"),
        "DISCORD_CHANNEL_ID": os.getenv("DISCORD_CHANNEL_ID"),
        "ENVIRONMENT": os.getenv("ENVIRONMENT", "development")  # Default to "development"
    }

    # Identify missing variables
    missing_vars = {key for key, value in required_vars.items() if not value}

    if missing_vars:
        logging.error(f"Missing critical environment variables: {', '.join(missing_vars)}")
        sys.exit(f"Cannot start bot without required variables: {', '.join(missing_vars)}")

    # Log validated variables for debugging (sensitive data like BOT_TOKEN should be sanitized)
    logging.debug(f"Environment Variables Loaded: {', '.join([f'{key}={value}' for key, value in required_vars.items() if key != 'BOT_TOKEN'])}")
    logging.debug("BOT_TOKEN=*** [REDACTED]")  # Avoid logging sensitive values like tokens

    return required_vars

env_vars = validate_env_vars()
BOT_TOKEN = env_vars["BOT_TOKEN"]
TARGET_CHANNEL_ID = int(env_vars["DISCORD_CHANNEL_ID"])

ENVIRONMENT = FILE_ENVIRONMENT.capitalize()


LOGS_FOLDER = "logs"
os.makedirs(LOGS_FOLDER, exist_ok=True)

account_mapping = load_account_mappings()

# Load the watchlist and initialize db when bot starts
load_watch_list()
init_db()


@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
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
        print(f"Could not find channel with ID: {TARGET_CHANNEL_ID}")

    print(startup_banner)
    print(tagline)
    global task
    logging.info(f"Initializing {APP_NAME} in {FILE_ENVIRONMENT} environment.")
    logging.info(f"{bot.user} has connected to Discord!")

    if task is None:
        task = asyncio.create_task(periodic_check(bot))
        logging.info("Periodic task started.")
    else:
        logging.info("Periodic task already running.")



@bot.command(name="restart")
async def restart(ctx):
    """Restarts the bot."""
    await ctx.send("\n(・_・ヾ)     (-.-)Zzz...\n")
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
        # Check if the message content matches any shortcut
        if message.content in shortcuts:
            # Replace the shortcut with its mapped full command
            message.content = shortcuts[message.content]

        # Continue with existing specific checks
        if message.content.lower().startswith("manual"):
            parse_manual_order_message(message.content)
        elif message.embeds:
            parse_embed_message(message.embeds[0])
        else:
            parse_order_message(message.content)

    # Pass the message to the command processing so bot commands work
    await bot.process_commands(message)


@bot.command(name="reminder", help="Shows daily reminder")
async def show_reminder(ctx):
    """Shows a daily reminder message."""
    await send_reminder_message_embed(ctx)


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


@bot.command(
    name="grouplist", help="Summary by account owner. Optional: specify a broker."
)
async def brokers_groups(ctx, broker: str = None):
    """
    Displays account owner summary for a specific broker or all brokers if no broker is specified.
    """
    embed = generate_broker_summary_embed(config, account_mapping, broker)
    await ctx.send(
        embed=(
            embed if embed else "An error occurred while generating the broker summary."
        )
    )


@bot.command(
    name="brokerwith",
    help="All brokers with specified tickers > brokerwith <ticker> (details)",
)
async def broker_has(ctx, ticker: str, *args):
    """Shows broker-level summary for a specific ticker."""
    specific_broker = args[0] if args else None
    await track_ticker_summary(
        ctx, ticker, show_details=bool(specific_broker), specific_broker=specific_broker
    )


@bot.command(
    name="watch",
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


@bot.command(
    name="addratio",
    help="Adds or updates the split ratio for an existing ticker in the watchlist.",
)
async def add_ratio(ctx, ticker: str, split_ratio: str):

    if not split_ratio:
        await ctx.send("Please include split ratio: * X-Y *")
        return

    await watch_ratio(ctx, ticker, split_ratio)


@bot.command(name="watchlist", help="Lists all tickers currently being watched.")
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

# Graceful shutdown handler
def shutdown_handler(signal_received, frame):
    logging.info("Shutting down the bot...")
    global task
    if task and not task.done():
        task.cancel()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# Start the bot with the token from the .env
if __name__ == "__main__":
    bot.run(BOT_TOKEN)