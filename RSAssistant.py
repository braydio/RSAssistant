import asyncio
import os
import json
import sys
from datetime import datetime

# Third-party imports
import discord
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord import Embed
from discord.ext import commands

# Local utility imports
from utils.config_utils import (all_account_nicknames, generate_broker_summary_embed, all_brokers_summary_by_owner,
                                all_brokers, load_config, account_mapping)
from utils.csv_utils import clear_holdings_log
from utils.excel_utils import index_account_details, get_excel_file_path, map_accounts_in_excel_log, clear_account_mappings
from utils.parsing_utils import parse_embed_message, parse_manual_order_message, parse_order_message
from utils.utility_utils import print_to_discord, track_ticker_summary
from utils.watch_utils import (list_watched_tickers, load_watch_list, periodic_check,
                               send_reminder_message, send_reminder_message_embed, stop_watching,
                               watch_ticker)

# Load configuration and initialize paths
config = load_config()
excel_log_file = get_excel_file_path()
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
MANUAL_ORDER_ENTRY_TXT = config['paths']['manual_orders']
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
FILE_VERSION = config['general_settings']['file_version']
FILE_NAME = config['general_settings']['app_name']

# Extract shortcuts and prefix
shortcuts = config.get('shortcuts', {})
prefix = config['discord']['prefix']
task = None

# Ensure that shortcuts use the correct prefix dynamically (optional step)
shortcuts = {f"{prefix}{key[len(prefix):]}": value for key, value in shortcuts.items()}

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = config['discord']['intents']['message_content']
intents.guilds = config['discord']['intents']['guilds']
intents.members = config['discord']['intents']['members']

# Initialize bot
bot = commands.Bot(command_prefix=config['discord']['prefix'], case_insensitive=True, intents=intents)

# Discord IDs and paths
TARGET_CHANNEL_ID = config['discord_ids']['channel_id']  
PERSONAL_USER_ID = config['discord_ids']['my_id']
TARGET_BOT_ID = config['discord_ids']['target_bot']  
LOGS_FOLDER = 'logs'
os.makedirs(LOGS_FOLDER, exist_ok=True)



# Load the watchlist when bot starts
load_watch_list()

@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    account_setup_message = f"\n\n**(╯°□°）╯**\n\n Account mappings not found. Please fill in Reverse Split Log > Account Details sheet at\n`{excel_log_file}`\n\nThen run: `..loadmap` and `..loadlog`."
    
    try:
        with open(ACCOUNT_MAPPING_FILE, 'r') as file:
            account_mappings = json.load(file)
        ready_message = account_setup_message if not account_mappings else '...watching for order activity...\n(✪‿✪)'
    except (FileNotFoundError, json.JSONDecodeError):
        ready_message = account_setup_message

    if channel:
        await channel.send(ready_message)
    else:
        print(f"Could not find channel with ID: {TARGET_CHANNEL_ID}")

    global task
    print(f'Initializing from {FILE_NAME} - version {FILE_VERSION}.')
    print(f'{bot.user} has connected to Discord!')

    if task is None:
        task = asyncio.create_task(periodic_check(bot))
        print("Periodic task started.")
    else:
        print("Periodic task already running.")


@bot.command(name="restart")
async def restart(ctx):
    """Restarts the bot by terminating the current process and starting a new one."""
    await ctx.send("\n(・_・ヾ)     (-.-)Zzz...\n")
    await asyncio.sleep(1)
    print("Attempting to restart the bot...")
    try:
        python = sys.executable
        os.execv(python, [python] + sys.argv)
    except Exception as e:
        print(f"Error during restart: {e}")
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


@bot.command(name='reminder', help='Shows daily reminder')
async def show_reminder(ctx):
    """Shows a daily reminder message."""
    await send_reminder_message_embed(ctx)


@bot.command(name='brokerlist', help='List all active brokers. Optional arg: Broker')
async def brokerlist(ctx, broker: str = None):
    """Lists all brokers or accounts for a specific broker."""
    try:
        if broker is None:
            await all_brokers(ctx)
        else:
            await all_account_nicknames(ctx, broker)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")


@bot.command(name='grouplist', help='Summary by account owner. Optional: specify a broker.')
async def brokers_groups(ctx, broker: str = None):
    """
    Displays account owner summary for a specific broker or all brokers if no broker is specified.
    """
    embed = generate_broker_summary_embed(config, account_mapping, broker)
    await ctx.send(embed=embed if embed else "An error occurred while generating the broker summary.")


@bot.command(name='brokerwith', help=' > brokerwith <ticker> (details)')
async def broker_has(ctx, ticker: str, *args):
    """Shows broker-level summary for a specific ticker."""
    specific_broker = args[0] if args else None
    await track_ticker_summary(ctx, ticker, show_details=bool(specific_broker), specific_broker=specific_broker)


@bot.command(name='watch', help='Adds a ticker to the watchlist for tracking.')
async def watch(ctx, ticker: str, split_date: str = None):
    """Adds a ticker to the watchlist with an optional split date."""
    if not split_date:
        await ctx.send("Please include split date: * mm/dd *")
        return
    await watch_ticker(ctx, ticker, split_date)


@bot.command(name='watchlist', help='Lists all tickers currently being watched.')
async def allwatching(ctx):
    """Lists all tickers being watched."""
    await list_watched_tickers(ctx)


@bot.command(name='watched', help='Removes a ticker from the watchlist.')
async def watched_ticker(ctx, ticker: str):
    """Removes a ticker from the watchlist."""
    await stop_watching(ctx, ticker)


@bot.command(name='todiscord', help='Prints text file one line at a time')
async def print_by_line(ctx):
    """Prints contents of a file to Discord, one line at a time."""
    await print_to_discord(ctx)


@bot.command(name='loadmap', help='Maps accounts from Account Details excel sheet')
async def load_account_mappings_command(ctx):
    """Maps account details from the Excel sheet to JSON."""
    try:
        await ctx.send("Mapping account details...")
        await index_account_details(ctx)
        await ctx.send("Mapping complete.\n Run `..loadlog` to save mapped accounts to the excel logger.")
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")


@bot.command(name='loadlog', help='Updates excel log with mapped accounts')
async def update_log_with_mappings(ctx):
    """Updates the Excel log with mapped accounts."""
    try:
        await ctx.send("Updating log with mapped accounts...")
        await map_accounts_in_excel_log(ctx)
        await ctx.send("Complete.")
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")


@bot.command(name='clearmap', help='Clears all account mappings from the account_mapping.json file')
async def clear_mapping_command(ctx):
    """Clears all account mappings from the JSON file."""
    try:
        await ctx.send("Clearing account mappings...")
        await clear_account_mappings(ctx)
        await ctx.send("Account mappings have been cleared.")
    except Exception as e:
        await ctx.send(f"An error occurred during the clearing process: {str(e)}")


@bot.command(name='clearholdings', help='Clears entries in holdings_log.csv')
async def clear_holdings(ctx):
    """Clears all holdings from the CSV file."""
    success, message = clear_holdings_log(HOLDINGS_LOG_CSV)
    await ctx.send(message if success else f"Failed to clear holdings log: {message}")


# Start the bot with the token from the config
if __name__ == "__main__":
    bot.run(config['discord']['token'])
