import discord
from discord.ext import commands
from discord import Embed
import os
import asyncio

# Import utility functions
from utils.config_utils import load_config, all_brokers
from utils.utility_utils import print_to_discord, track_ticker_summary, profile
from utils.watch_utils import (
    load_watch_list, watch_ticker, check_watchlist_positions, 
    watch_ticker_status, list_watched_tickers, stop_watching, list_watched_tickers_embed
)
from utils.csv_utils import save_holdings_to_csv, read_holdings_log
from utils.parsing_utils import parse_order_message, parse_embed_message, parse_manual_order_message
from utils.excel_utils import update_excel_log

# Load configuration and holdings data
config = load_config()
holdings_data = read_holdings_log()
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
MANUAL_ORDER_ENTRY_TXT = config['paths']['manual_orders']

# Set up the bot intents
intents = discord.Intents.default()
intents.message_content = config['discord']['intents']['message_content']
intents.guilds = config['discord']['intents']['guilds']
intents.members = config['discord']['intents']['members']

# Initialize the bot with prefix and intents
bot = commands.Bot(command_prefix=config['discord']['prefix'], intents=intents)

# Channel ID and bot IDs
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
    print(f'{bot.user} has connected to Discord!')

async def periodic_check():
    """Checks watchlist against saved holdings for stock purchases."""
    while True:
        await check_watchlist_positions()
        await asyncio.sleep(86400)  # Check daily

# Command to display which accounts need to buy a watched ticker
@bot.command(name='remindme', help='Checks for brokers, accounts with / without stock in holdings.')
async def check_for_ticker(ctx, *args):
    show_accounts = "details" in args
    await check_watchlist_positions(ctx, show_accounts)
      
# Event triggered when a message is received
@bot.event
async def on_message(message):
    if message.channel.id == TARGET_CHANNEL_ID: #and message.author.id == TARGET_BOT_ID:
        # Check for 'manual' keyword to handle manual order updates
        if message.content.lower().startswith("manual"):
            # Parse the manual order details
            order_details = parse_manual_order_message(message.content)
            if order_details:
                # Prepare the order tuple and update Excel
                orders = [(
                    order_details['broker_name'],
                    order_details['account'],
                    order_details['order_type'],
                    order_details['stock'],
                    None,  # quantity not needed
                    None,  # date not needed
                    order_details['price']
                )]
                update_excel_log(orders, order_details['order_type'], "path_to_excel_file.xlsx")
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
@bot.command(name='brokerlist', help='List all active brokers')
async def list_brokers(ctx):
    # Get the list of brokers
    brokers = all_brokers()
    
    if brokers:
        # Format the list as a string to send to the Discord channel
        broker_list = "\n".join(brokers)
        await ctx.send(f"**Active Brokers:**\n{broker_list}")
    else:
        await ctx.send("No active brokers found or an error occurred.")

# Command to show the summary for a broker
@bot.command(name='broker', help='Summary totals for a broker')
async def broker_profile(ctx, broker_name: str):
    await profile(ctx, broker_name)

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
        await ctx.send("Please include split date. (Format: MM/DD, MM/DD/YYYY, YYYY-MM-DD)")
        return
    
    await watch_ticker(ctx, ticker, split_date)

# Command to display the progress of a watched ticker
@bot.command(name='watching', help='Displays a summary for a watched ticker.')
async def track(ctx, ticker: str):
    await watch_ticker_status(ctx, ticker)


""" # Command to get the status of a specific ticker
@bot.command(name='watchstatus', help='Displays a broker-level summary for a ticker.')
async def watchstatus(ctx, ticker: str):
    await get_watch_status(ctx, ticker)
 """
# Command to list all watched tickers
@bot.command(name='watchlist', help='Lists all tickers currently being watched.')
async def allwatching(ctx):
    await list_watched_tickers(ctx)

# Command to list all watched tickers as embed message
@bot.command(name='cleanlist', help='Lists all tickers currently being watched.')
async def allwatching(ctx):
    await list_watched_tickers_embed(ctx)

# Command to stop watching a stock ticker
@bot.command(name='watched', help='Removes a ticker from the watchlist.')
async def watched_ticker(ctx, ticker: str):
    await stop_watching(ctx, ticker)



# Command to trigger printing a file to Discord one line at a time
@bot.command(name='todiscord', help='Prints a file one line at a time')
async def print_by_line(ctx):
    # Call the function to print the file to Discord
    await print_to_discord(ctx)

# Start the bot with the token from the config
if __name__ == "__main__":
    bot.run(config['discord']['token'])
