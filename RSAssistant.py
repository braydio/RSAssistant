import csv
import asyncio
import json
import logging
import os
import sys
import signal
import shutil
import time
from datetime import datetime, timedelta

# Third-party imports
import discord 
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord import Embed
from discord.ext import commands

# Local utility imports
from utils.config_utils import (load_config, 
    DISCORD_TOKEN, EXCEL_FILE_MAIN, ACCOUNT_MAPPING, WATCH_FILE,
    DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL,
    HOLDINGS_LOG_CSV, ORDERS_LOG_CSV, SQL_DATABASE_DB_V1, VERSION
)
# Webdriver imports
from utils.Webdriver_FindFilings import fetch_results
from utils.Webdriver_Scraper import StockSplitScraper

from utils.history_query import show_sql_holdings_history 
from utils.excel_utils import (clear_account_mappings, add_account_mappings, index_account_details,
                               map_accounts_in_excel_log)
from utils.parsing_utils import (parse_embed_message, alert_channel_message,
                                 parse_order_message)
from utils.sql_utils import get_db_connection, init_db, bot_query_database
from utils.csv_utils import clear_holdings_log, send_top_holdings_embed, sell_all_position
from utils.utility_utils import (all_account_nicknames, all_brokers,
                                 generate_broker_summary_embed,
                                 print_to_discord, track_ticker_summary,
                                 update_file_version, get_file_version, get_last_stock_price)
from utils.watch_utils import (watch_list_manager, periodic_check, send_reminder_message_embed)
from utils.order_exec import send_sell_command, schedule_and_execute

bot_info = (f'RSAssistant - v{VERSION} by @braydio \n    <https://github.com/braydio/RSAssistant> \n \n ')

init_db()
config = load_config()

CONFIG_TOKEN = "ERROR : Cannot locate critical environment variable  : BOT_TOKEN" # config["discord"]["token"]
CONFIG_CHANNEL_PRIMARY = "ERROR : Cannot locate critical environment variable  : DISCORD PRIMARY CHANNEL" # config["discord"]['channel_id']
CONFIG_CHANNEL_SECONDARY = "ERROR : Cannot locate critical environment variable  : DISCORD SECONDARY CHANNEL" # config["discord"]['channel_id2']
# Chapt Environment variables

TARGET_CHANNEL_ID = DISCORD_PRIMARY_CHANNEL
ALERTS_CHANNEL_ID = DISCORD_SECONDARY_CHANNEL
BOT_TOKEN = DISCORD_TOKEN

logging.info(f"Environment Variables loaded from dotenv : BOT_TOKEN {BOT_TOKEN}, PRIMARY CHANNEL ID {DISCORD_PRIMARY_CHANNEL}, SECONDARY CHANNEL ID {DISCORD_SECONDARY_CHANNEL}")

logging.info(f"Holdings Log CSV file: {HOLDINGS_LOG_CSV}")
logging.info(f"Orders Log CSV file: {ORDERS_LOG_CSV}")

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# Initialize bot
bot = commands.Bot(
    command_prefix="..", case_insensitive=True, intents=intents
)

@bot.command(name="order", help="Schedule a buy or sell order. Usage: `..order <buy/sell> <ticker> [quantity] <broker> <dry_mode> <time>`")
async def process_order(ctx, action: str, quantity: float = 1, ticker: str = None, broker: str = "all", dry_mode: str = "false", time: str = None):
    """
    Processes and schedules a buy or sell order. Defaults:
    - Action: 'buy' or 'sell'
    - Quantity: 1
    - Broker: all
    - Dry mode: false
    - Time: Executes immediately if not specified.
    Supports scheduling:
    - HH:MM time from now
    - mm/dd date
    - HH:MM time on mm/dd date
    """
    try:
        # Validate action
        if action.lower() not in ["buy", "sell"]:
            await ctx.send("Invalid action. Use 'buy' or 'sell'.")
            return

        # Validate quantity
        if quantity <= 0:
            await ctx.send("Quantity must be greater than 0.")
            return

        # Validate dry_mode
        if dry_mode.lower() not in ["true", "false"]:
            await ctx.send("Invalid dry mode. Use 'true' or 'false'.")
            return

        now = datetime.now()
        execution_time = None

        # Validate and parse time
        if time:
            try:
                if "/" in time:  # Check if a date is included
                    if " " in time:  # HH:MM on mm/dd
                        date_part, time_part = time.split(" ")
                        month, day = map(int, date_part.split("/"))
                        hour, minute = map(int, time_part.split(":"))
                        await ctx.send(f"Scheduled {action} order: {quantity} {ticker.upper()} via {broker} in {'dry run' if dry_mode == 'true' else 'live'} mode ")
                        execution_time = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    else:  # mm/dd only
                        month, day = map(int, time.split("/"))
                        execution_time = now.replace(month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
                else:  # HH:MM time only
                    hour, minute = map(int, time.split(":"))
                    execution_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if execution_time < now:
                    execution_time += timedelta(days=1)  # Adjust for next day if time has passed
            except ValueError:
                await ctx.send("Invalid time format. Use HH:MM, mm/dd, or HH:MM on mm/dd.")
                return
        else:
            execution_time = now  # Execute immediately if no time is specified

        # Schedule the order using logic in `order_exec.py`
        await schedule_and_execute(ctx, action, ticker, quantity, broker, dry_mode, execution_time)

        await ctx.send(f"!rsa {action} {quantity} {ticker.upper()} {broker} {'dry' if dry_mode == 'true' else 'false'}")
        await ctx.send(f"for {execution_time.strftime('%Y-%m-%d %H:%M:%S')}.")

        logging.info(f"Scheduled {action} order: {ticker}, quantity: {quantity}, broker: {broker}, dry_mode: {dry_mode}, time: {execution_time}.")

    except Exception as e:
        logging.error(f"Error scheduling {action} order: {e}")
        await ctx.send(f"An error occurred: {str(e)}")

global periodic_task, reminder_scheduler

@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    
    await asyncio.sleep(2)
    logging.info(f"RSAssistant by @braydio - GitHub: https://github.com/braydio/RSAssistant")
    logging.info(f"Version {VERSION} | Runtime Environment: Production")
    await asyncio.sleep(3)
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    
    account_setup_message = f"\n\n**(╯°□°）╯**\n\n Account mappings not found. Please fill in Reverse Split Log > Account Details sheet at\n`{EXCEL_FILE_MAIN}`\n\nThen run: `..loadmap` and `..loadlog`."
    
    try:
        ready_mapped = ACCOUNT_MAPPING
        ready_message = (
            account_setup_message
            if not ready_mapped
            else "...watching for order activity...\n(✪‿✪)"
        )
    except (FileNotFoundError, json.JSONDecodeError):
        ready_message = account_setup_message
        
    if channel:
        await channel.send(ready_message)
    else:
        logging.warning(f"Target Channel not found - ID: {TARGET_CHANNEL_ID} on startup.")

    logging.info(f"Initializing Application in Production environment.")
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

@bot.command(name="liquidate", help="Liquidate holdings for a brokerage. Usage: `..liquidate <broker> [test_mode=false]`")
async def liquidate(ctx, broker: str, test_mode: str = "false"):
    """
    Liquidates all holdings for a given brokerage.
    - Checks the holdings log for the brokerage.
    - Sells the maximum quantity for each stock.
    - Runs the sell command for each stock with a 30-second interval.
    
    Args:
        broker (str): The name of the brokerage to liquidate.
        live_mode (str): Set to "true" for live mode or "false" for dry run mode. Defaults to "false".
    """
    try:
        logging.info(f"Liquidate position order logged for {broker}")
        await sell_all_position(ctx, broker, test_mode)

    except Exception as e:
        logging.error(f"Error during liquidation: {e}")
        await ctx.send(f"An error occurred: {str(e)}")    

@bot.command(name="restart")
async def restart(ctx):
    """Restarts the bot."""
    await ctx.send("\n(・_・ヾ)     (-.-)Zzz...\n")
    await ctx.send("AYO WISEGUY THIS COMMAND IS BROKEN AND WILL BE DISRUPTIVE TO THE DISCORD BOT! NICE WORK GENIUS!")
    logging.debug("The command now works as intended, but I like the message.")
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
            logging.warning(f"Manual order detected: {message.content}")
            # manual_order(message.content)
        elif message.embeds:
            parse_embed_message(message.embeds[0])
        else:
            parse_order_message(message.content)
    
    if message.channel.id == ALERTS_CHANNEL_ID:
        if message.content:
            logging.info(f"Received message: {message.content}")
            
            channel = bot.get_channel(TARGET_CHANNEL_ID)
            content = message.content

            match = alert_channel_message(content)

            if match:
                title = match.group(1)  # Extract the full title
                ticker = match.group(2)  # Extract the stock ticker
                url = match.group(3)  # Extract the URL

                logging.info(f"Nasdaq Feed: {title} {ticker} {url}")

                # Detect "Reverse Stock Split" in the title
                if "Reverse Stock Split" in title:
                    action = "Reverse Stock Split"
                else:
                    action = "Corporate Action"

                # Format the alert message
                alert_message = (
                    f"🚨 Nasdaq Corporate Actions Alert:\n"
                    f"**{ticker} {action}**\n"
                    f"[Details Here]({url})"
                )
                logging.info("Alert Message")
                channel.send(alert_message)

            # Pass the message to the command processing so bot commands work
    await bot.process_commands(message)

    logging.warning("No match found in content for alert message. Content may not follow the expected pattern.")
    return None  # Return None if no match is found

@bot.command(name="reminder", help="Shows daily reminder")
async def show_reminder(ctx):
    """Shows a daily reminder message."""
    await send_reminder_message_embed(ctx)

async def send_scheduled_reminder():
    """Send scheduled reminders to the target channel."""
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel:
        await send_reminder_message_embed(channel)
    else:
        logging.error(f"Could not find channel with ID: {DISCORD_PRIMARY_CHANNEL} to send reminder.")

@bot.command(name="tosell", help="Usage: `..addsell <ticker>` Add a ticker to the sell list. ")
async def add_to_sell(ctx, ticker: str):
    """Add a ticker to the sell list."""
    ticker = ticker.upper()
    watch_list_manager.add_to_sell_list(ticker)
    await ctx.send(f"Added {ticker} to the sell list.")


@bot.command(name="nosell", help="Remove a ticker from the sell list. Usage: `..removesell <ticker>`")
async def remove_sell(ctx, ticker: str):
    """Remove a ticker from the sell list."""
    ticker = ticker.upper()
    if watch_list_manager.remove_from_sell_list(ticker):
        await ctx.send(f"Removed {ticker} from the sell list.")
    else:
        await ctx.send(f"{ticker} was not in the sell list.")


@bot.command(name="selling", help="View the current sell list.")
async def view_sell_list(ctx):
    """Display the current sell list."""
    sell_list = watch_list_manager.get_sell_list()
    if not sell_list:
        await ctx.send("The sell list is empty.")
    else:
        embed = discord.Embed(
            title="Sell List",
            description="Tickers flagged for selling:",
            color=discord.Color.red(),
        )
        for ticker, details in sell_list.items():
            added_on = details.get("added_on", "N/A")
            embed.add_field(name=ticker, value=f"Added on: {added_on}", inline=False)
        await ctx.send(embed=embed)


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

    await watch_list_manager.watch_ticker(ctx, ticker, split_date, split_ratio)


@bot.command(name="addratio",
    help="Adds or updates the split ratio for an existing ticker in the watchlist.",
)
async def add_ratio(ctx, ticker: str, split_ratio: str):

    if not split_ratio:
        await ctx.send("Please include split ratio: * X-Y *")
        return

    await watch_list_manager.watch_ratio(ctx, ticker, split_ratio)


@bot.command(name="watchlist",
    help="Lists all tickers currently being watched.")
async def allwatching(ctx):
    """Lists all tickers being watched."""
    await watch_list_manager.list_watched_tickers(ctx)


@bot.command(name="watched", help="Removes a ticker from the watchlist.")
async def watched_ticker(ctx, ticker: str):
    """Removes a ticker from the watchlist."""
    await watch_list_manager.stop_watching(ctx, ticker)


@bot.command(name="todiscord", help="Prints text file one line at a time")
async def print_by_line(ctx):
    """Prints contents of a file to Discord, one line at a time."""
    await print_to_discord(ctx)


@bot.command(
    name="addmap",
    help="Usage: addmap <brokerage> <broker_no> <account (last 4)> <Account Nickname> | Adds mapping details for an account to the Account Mappings file."
)
async def add_account_mappings_command(ctx, brokerage: str, broker_no: str, account: str, nickname: str):
    try:
        # Validate the inputs
        if not (brokerage and broker_no and account and nickname):
            await ctx.send("All arguments are required: `<brokerage> <broker_no> <account> <nickname>`.")
            return

        await add_account_mappings(ctx, brokerage, broker_no, account, nickname)
    except Exception as e:
        logging.info(f"An error ocurred: {e}")

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


@bot.command(
    name="websearch",
    help=(
        "Surfin' the Web!\n\n"
        "**Arguments:**\n"
        "`mode` (required): The mode of operation. Choose from:\n"
        "  - `search <ticker>`: Search for splits for a specific ticker.\n"
        "  - `report`: Generate a weekly report of stock splits.\n"
        "  - `custom <start_date> <end_date>`: Fetch splits for a custom date range (YYYY-MM-DD).\n"
        "`args` (optional): Additional arguments depending on the mode."
    ),
    brief="Search stock splits",
    category="Web Search"
)
async def websearch(ctx, mode: str, *args):
    """
    Handles web search commands for stock splits.

    Args:
        ctx (commands.Context): The context of the command.
        mode (str): The mode of operation ('search', 'report', 'custom').
        args (tuple): Additional arguments for the selected mode.
    """
    scraper = StockSplitScraper()

    if mode == "search" and args:
        ticker = args[0]
        await scraper.run(ctx, mode="search_ticker", ticker=ticker)
    elif mode == "report":
        await scraper.run(ctx, mode="weekly_report")
    elif mode == "custom" and len(args) == 2:
        start_date, end_date = args
        await scraper.run(ctx, mode="custom_report", custom_dates=(start_date, end_date))
    await ctx.send(
        "Invalid usage. Try one of the following:\n"
        "`..websearch search <ticker>`\n"
        "`..websearch report`\n"
        "`..websearch custom <start_date> <end_date>`"
    )


@bot.command(
    name="rsasearch",
    help=(
        "Fetch recent filings related to reverse stock splits.\n\n"
        "**Optional Arguments:**\n"
        "- `excerpt`: Include excerpts from filings that match the search terms.\n"
        "- `summary`: Provide a summary of the results instead of a detailed list."
    )
)
async def rs_roundup(ctx, *args):
    include_excerpt = "excerpt" in args
    summary = "summary" in args

    await ctx.send("Fetching filings, please wait...")
    results = fetch_results(include_excerpt=include_excerpt)

    if isinstance(results, str):  # Check for error message
        await ctx.send(results)
    elif results:
        if summary:
            message = (
                f"**Summary**:\n"
                f"Total Results: {len(results)}\n"
                f"Forms: {', '.join(set(r['form_type'] for r in results))}\n"
                f"Companies: {', '.join(set(r['company_name'] for r in results))}\n"
            )
            await ctx.send(message)
        else:
            for result in results:
                message = (
                    f"**Company**: {result['company_name']}\n"
                    f"**Form Type**: {result['form_type']}\n"
                    f"**Description**: {result['description']}\n"
                    f"**File Date**: {result['file_date']}\n"
                )
                if include_excerpt:
                    message += f"**Excerpt**: {result['excerpt']}\n"
                await ctx.send(message)
    else:
        await ctx.send("No relevant filings found.")


@bot.command(
    name="sql",
    help=(
        "Query a table from the database.\n\n"
        "**Arguments:**\n"
        "- `table`: Name of the table to query (e.g., Orders, Holdings).\n"
        "- `filters`: Optional key=value pairs for filtering (e.g., ticker=AAPL).\n"
        "- `limit`: Optional row limit (e.g., limit=5)."
    ),
)
async def query_table(ctx, table_name: str, *args):
    try:
        results = bot_query_database(table_name, filters=None, order_by=None, limit=None)
        if not results:
            await ctx.send(f"No results found for table `{table_name}` with the provided filters.")
            return

        # Send results as a message
        response = ""
        for row in results:
            response += "\n".join([f"{key}: {value}" for key, value in row.items()]) + "\n\n"
        
        # Send response (Discord limits messages to 2000 characters)
        for chunk in [response[i:i+2000] for i in range(0, len(response), 2000)]:
            await ctx.send(chunk)
    except Exception as e:
        await ctx.send(f"Error querying table `{table_name}`: {e}")

@bot.command(name="history", help="Shows historical holdings over time from the database. Usage: `..history <account> <ticker> <start_date> <end_date>`")
async def sql_historical_holdings(ctx, account: str = None, ticker: str = None, start_date: str = None, end_date: str = None):
    """
    Displays historical holdings over time from the SQL database.
    """
    await show_sql_holdings_history(ctx, account, ticker, start_date, end_date)


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
        channel = bot.get_channel(DISCORD_SECONDARY_CHANNEL)

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


@bot.command(
    name="shutdown",
    help="Gracefully shuts down the bot.",
    brief="Stop the bot",
    category="Admin"
    )
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



# Start the bot with the token from the .env
if __name__ == "__main__":
    bot.run(BOT_TOKEN)  
