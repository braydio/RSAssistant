import asyncio
# Imports from standard libraries
import os
import json
import sys
from datetime import datetime

# Imports from third-party libraries
import discord
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord import Embed
from discord.ext import commands

# Imports from local utility modules
# Import utility functions
from utils.config_utils import (all_account_nicknames, all_account_numbers,
                                all_brokers, all_brokers_groups, load_config)
from utils.csv_utils import read_holdings_log, save_holdings_to_csv
from utils.excel_utils import index_account_details, map_accounts_in_excel_log, update_excel_log
from utils.parsing_utils import (parse_embed_message,
                                 parse_manual_order_message,
                                 parse_order_message)
from utils.utility_utils import print_to_discord, profile, track_ticker_summary
from utils.watch_utils import (list_watched_tickers,
                               load_watch_list, periodic_check,
                               send_reminder_message,
                               send_reminder_message_embed, stop_watching,
                               watch_ticker)

# Load configuration and holdings data
config = load_config()
holdings_data = read_holdings_log()
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
MANUAL_ORDER_ENTRY_TXT = config['paths']['manual_orders']
EXCEL_FILE_PATH = config['paths']['excel_log']
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
task = None

# Set up the bot intents
intents = discord.Intents.default()
intents.message_content = config['discord']['intents']['message_content']
intents.guilds = config['discord']['intents']['guilds']
intents.members = config['discord']['intents']['members']

# Initialize the bot with prefix and intents
bot = commands.Bot(command_prefix=config['discord']['prefix'], case_insensitive=True, intents=intents)

# Discord IDs
TARGET_CHANNEL_ID = config['discord_ids']['channel_id']  
PERSONAL_USER_ID = config['discord_ids']['my_id']
TARGET_BOT_ID = config['discord_ids']['target_bot']  

# Ensure the logs folder exists
LOGS_FOLDER = 'logs'
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Load the watchlist when the bot starts
load_watch_list()

# Event triggered when the bot is ready
@bot.event
async def on_ready():
    # Bot initialized
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    ready_message = f'\nRSAssistant-bot watching for order activity...\n (✪‿✪)' 
    
# Check if the account_mapping.json file exists and has content
    try:
        account_setup_message = f"\n\n**(╯°□°）╯**\n\n Account mappings not found. Please fill in Reverse Split Log > Account Details sheet at\n`{EXCEL_FILE_PATH}`\n\nThen run: `..updatemapping` and `..updatelog`."
        
        with open(ACCOUNT_MAPPING_FILE, 'r') as file:
            account_mappings = (json.load(file))
        
        # ( •́ _ •̀ )  (⌐■_■)  (ಥ﹏ಥ)   (-.-)Zzz...

        # Check if there are mappings present in the file
        if not account_mappings:  # Empty dictionary
            ready_message = account_setup_message
        else:
            ready_message = f'\nWatching for order activity...\n\n(✪‿✪)'

    except FileNotFoundError:
            ready_message = account_setup_message
    except json.JSONDecodeError:
            ready_message = account_setup_message

    # Send the message to the channel
    if channel:
        await channel.send(ready_message)
    else:
        print(f"Could not find channel with ID: {TARGET_CHANNEL_ID}")

    global task
    print(f'{bot.user} has connected to Discord!')

    if task is None:
        task = asyncio.create_task(periodic_check(bot))
        print("Periodic task started.")
    else:
        print("Periodic task already running.")


# Replace 'bot' with your instance of commands.Bot or commands.AutoShardedBot
@bot.command(name="restart")
# @commands.is_owner()  # Only allow the bot owner to use this command
async def restart(ctx):
    """Restarts the bot by terminating the current process and starting a new one."""
    await ctx.send("\n(・_・ヾ)     (-.-)Zzz...\n")
    
    # Wait a moment to ensure the message is sent before restarting
    await asyncio.sleep(1)
    python = sys.executable

    # Properly terminate the current bot process and replace it with a new one
    os.execv(python, [python] + sys.argv)

async def reminder_message():
    """Checks watchlist against saved holdings for stock purchases."""
    while True:
        await()

# -- CURRENTLY WORKING ON

@bot.command(name='updatemapping', help='Maps accounts from Account Details excel sheet')
async def excel_details_to_json(ctx):
    try:
        await ctx.send("Mapping account details...")
        await index_account_details(ctx)
        await ctx.send("Mapping complete.\n Run `..updatelog` to save mapped accounts to the excel logger.")
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")


@bot.command(name='updatelog', help='Updates excel log with mapped accounts')
async def excel_details_to_json(ctx):
    try:
        await ctx.send("Updating logger with mapped accounts")
        await map_accounts_in_excel_log(ctx)
        await ctx.send("Complete")
    except Exception as e:
        await ctx.send(f"An error occurred during update: {str(e)}")

# Command to show the summary for a broker
@bot.command(name='broker', help='Summary totals for a broker')
async def broker_profile(ctx, broker_name: str):
    await profile(ctx, broker_name)

# --
      
# Event triggered when a message is received
@bot.event
async def on_message(message):
    print(message.content.lower())
    if message.channel.id == TARGET_CHANNEL_ID: #and message.author.id == TARGET_BOT_ID:
        # Check for 'manual' keyword to handle manual order updates
        if message.content.lower().startswith("manual"):
            # Parse the manual order details
            order_details = parse_manual_order_message(message.content)
            if order_details:
                # Prepare the order tuple and update Excel
                orders = [(
                    order_details['broker_name'],
                    order_details['group_number'],
                    order_details['account'],
                    order_details['order_type'],
                    order_details['stock'],
                    None,  # quantity not needed
                    None,  # date not needed
                    order_details['price']
                )]
                update_excel_log(orders, order_details['order_type'], EXCEL_FILE_PATH)
        elif message.content.lower().startswith("**"):
            print("No ")
        else:
            # Call the regular order parsing function for non-manual messages
            parse_order_message(message.content)

        # Handle embedded messages (updates holdings)
        if message.embeds:
            embed = message.embeds[0]
            print("Embeds here:")
            print(embed)
            parse_embed_message(embed, HOLDINGS_LOG_CSV)
            print(f"Holdings data saved to CSV for broker {embed.title.split(' Holdings')[0]}.")

    await bot.process_commands(message)

# Command to show the summary for a broker
@bot.command(name='reminder', help='Shows daily reminder')
async def show_message(ctx):
    await send_reminder_message_embed(ctx)

# Command to show the summary for a broker
@bot.command(name='brokerlist', help='List all active brokers. Optional arg: Broker ')
async def brokerlist(ctx, broker: str = None, account_info: str = None):
    """
    Command to list all brokers or the accounts for a specific broker.
    Usage:
    - ..brokerlist: Lists all brokers.
    - ..brokerlist 'broker' : Lists the accounts for broker.
    """
    try:
        # If no broker is provided, list all brokers
        if broker is None:
            await all_brokers(ctx)
            # await ctx.send(f"Available brokers: {brokers}")
            # return
        
        # If broker and 'accounts' is provided, list account nicknames or numbers
        else:
            await all_account_nicknames(ctx, broker)
        
        # If the command is invalid, send an error message
            
    except Exception as e:
        # Handle any unexpected errors
        await ctx.send(f"An error occurred: {str(e)}")

# Command to show the summary for a broker
@bot.command(name='grouplist', help='Shows daily reminder')
async def brokers_groups(ctx):
    await all_brokers_groups(ctx)

# Command to check which brokers hold the ticker
@bot.command(name='brokerwith', help=' > brokerwith <ticker> (details) ')
async def broker_has(ctx, ticker: str, *args):
    show_details = "details" in args
    # Check if "details" argument is passed
    await track_ticker_summary(ctx, ticker, show_details)

# Command to watch a stock
@bot.command(name='watch', help='Adds a ticker to the watchlist for tracking.')
async def watch(ctx, ticker: str, split_date: str = None):
    # Check if the split date is provided
    if not split_date:
        await ctx.send("Please include split date: * mm/dd *")
        return
    
    await watch_ticker(ctx, ticker, split_date)

# Command to list all watched tickers
@bot.command(name='watchlist', help='Lists all tickers currently being watched.')
async def allwatching(ctx):
    await list_watched_tickers(ctx)

# Command to stop watching a stock ticker
@bot.command(name='watched', help='Removes a ticker from the watchlist.')
async def watched_ticker(ctx, ticker: str):
    await stop_watching(ctx, ticker)

# Command to trigger printing a file to Discord one line at a time, useful for manual orders
@bot.command(name='todiscord', help='Prints text file one line at a time')
async def print_by_line(ctx):
    # Call the function to print the file to Discord
    await print_to_discord(ctx)


# WIP Commands: 


""" # Command to get the status of a specific ticker
@bot.command(name='watchstatus', help='Displays a broker-level summary for a ticker.')
async def watchstatus(ctx, ticker: str):
    await get_watch_status(ctx, ticker)
 """

# Start the bot with the token from the config
if __name__ == "__main__":
    bot.run(config['discord']['token'])
