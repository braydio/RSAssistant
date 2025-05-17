import asyncio
import csv
import json
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timedelta

# Third-party imports
import discord
import discord.gateway
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord import Embed
from discord.ext import commands

# Local utility imports
from utils.logging_setup import logger

from utils.config_utils import (
    BOT_TOKEN,
    DISCORD_PRIMARY_CHANNEL,
    DISCORD_SECONDARY_CHANNEL,
    EXCEL_FILE_MAIN,
    HOLDINGS_LOG_CSV,
    ORDERS_LOG_CSV,
    ACCOUNT_MAPPING,
)

from utils.csv_utils import (
    clear_holdings_log,
    sell_all_position,
    send_top_holdings_embed,
)
from utils.excel_utils import (
    add_account_mappings,
    clear_account_mappings,
    index_account_details,
    map_accounts_in_excel_log,
)
from utils.order_exec import process_sell_list, schedule_and_execute
from utils.autobuy_utils import autobuy_ticker
from utils.order_queue_manager import (
    add_to_order_queue,
    get_order_queue,
    remove_order,
    list_order_queue,
)
from utils.sql_utils import bot_query_database, get_db_connection, init_db
from utils.policy_resolver import SplitPolicyResolver
from utils.utility_utils import (
    all_account_nicknames,
    all_brokers,
    generate_broker_summary_embed,
    print_to_discord,
    track_ticker_summary,
)
from utils.on_message_utils import handle_on_message, set_channels
from utils.watch_utils import (
    periodic_check,
    send_reminder_message_embed,
    watch_list_manager,
)

bot_info = (
    "RSAssistant by @braydio \n    <https://github.com/braydio/RSAssistant> \n \n "
)

init_db()

logger.info(f"Holdings Log CSV file: {HOLDINGS_LOG_CSV}")
logger.info(f"Orders Log CSV file: {ORDERS_LOG_CSV}")

# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True


discord.gateway.DiscordWebSocket.resume_timeout = 60  # seconds
discord.gateway.DiscordWebSocket.gateway_timeout = 60  # seconds

# Initialize bot
bot = commands.Bot(
    command_prefix="..", case_insensitive=True, intents=intents, reconnect=True
)

periodic_task = None
reminder_scheduler = None


@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    global periodic_task
    now = datetime.now()

    logger.info(
        f"RSAssistant by @braydio - GitHub: https://github.com/braydio/RSAssistant"
    )
    logger.info(f"V3.1 | Running in CLI | Runtime Environment: Production")

    # Fetch the primary channel
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)

    # Prepare account setup message
    account_setup_message = (
        f"**(╯°□°）╯**\n\n"
        f"Account mappings not found. Please fill in Reverse Split Log > Account Details sheet at\n"
        f"`{EXCEL_FILE_MAIN}`\n\n"
        f"Then run: `..loadmap` and `..loadlog`."
    )

    try:
        ready_message = (
            account_setup_message
            if not ACCOUNT_MAPPING
            else "...watching for order activity...\n(✪‿✪)"
        )
    except (FileNotFoundError, json.JSONDecodeError):
        ready_message = account_setup_message

    # Send ready message to the primary channel
    if channel:
        await channel.send(
            f"{ready_message}\nThe time is {now.strftime('%m-%d %H:%M')}"
            f"Orders Log at {ORDERS_LOG_CSV}"
            f"Holdings Log at {HOLDINGS_LOG_CSV}"
        )
    else:
        logger.warning(
            f"Target channel not found - ID: {DISCORD_PRIMARY_CHANNEL} on startup."
        )
    logger.info(f"Initializing Application in Production environment.")
    logger.info(
        f"{bot.user} has connected to Discord! PRIMARY | {DISCORD_PRIMARY_CHANNEL}, SECONDARY | {DISCORD_SECONDARY_CHANNEL}"
    )
    set_channels(DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL)

    # Check if the periodic task is already running, and start it if not
    if "periodic_task" not in globals() or periodic_task is None:
        periodic_task = asyncio.create_task(periodic_check(bot))
        logger.info("Periodic check task started.")
    else:
        logger.info("Periodic check task is already running.")

    # Schedule reminder task using APScheduler
    global reminder_scheduler
    if reminder_scheduler is None:
        reminder_scheduler = BackgroundScheduler()
        reminder_scheduler.add_job(
            lambda: bot.loop.create_task(send_reminder_message_embed(bot)),
            CronTrigger(hour=8, minute=45),
        )
        reminder_scheduler.add_job(
            lambda: bot.loop.create_task(send_reminder_message_embed(bot)),
            CronTrigger(hour=15, minute=30),
        )
        reminder_scheduler.start()
        logger.info("Scheduled reminders at 8:45 AM and 3:30 PM started.")
    else:
        logger.info("Reminder scheduler already running.")


async def process_sell_list(bot):
    """Checks the sell list and executes due sell orders."""
    try:
        now = datetime.now()
        sell_list = watch_list_manager.sell_list

        # Iterate over sell list items
        for ticker, details in list(
            sell_list.items()
        ):  # Use list() to safely modify during iteration
            scheduled_time = datetime.strptime(
                details["scheduled_time"], "%Y-%m-%d %H:%M:%S"
            )

            if now >= scheduled_time:  # Check if the order's time has come
                # Construct the sell command
                command = f"!rsa sell {details['quantity']} {ticker} {details['broker']} false"

                # Send the sell command
                channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
                if channel:
                    await channel.send(command)
                    logger.info(
                        f"Executed sell order for {ticker} via {details['broker']}"
                    )

                # Remove the executed order from the sell list
                del sell_list[ticker]
                watch_list_manager.save_sell_list()
                logger.info(f"Removed {ticker} from sell list after execution.")

    except Exception as e:
        logger.error(f"Error processing sell list: {e}")


@bot.command(name="queue", help="View all scheduled orders.")
async def show_order_queue(ctx):
    queue = list_order_queue()
    if not queue:
        await ctx.send("There are no scheduled orders.")
    else:
        message = "**Scheduled Orders:**\n" + "\n".join(queue)
        await ctx.send(message)


@bot.command(
    name="ord",
    help="Schedule a buy or sell order. Usage: `..ord <buy/sell> <ticker> <broker> [quantity] <time>`",
)
async def process_order(
    ctx,
    action: str,
    ticker: str = None,
    broker: str = "all",
    quantity: float = 1,
    time: str = None,
):
    try:
        now = datetime.now()
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

        if market_open <= now <= market_close:
            execution_time = now
            logger.info(
                f"Executing order {action.upper()} {ticker.upper()} now, market is open"
            )
            await ctx.send(
                f"Executing {action.upper()} {ticker.upper()} immediately (market open)."
            )
        else:
            # Market closed, schedule next open
            execution_time = now
            if now >= market_close:
                execution_time = (now + timedelta(days=1)).replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
            elif now < market_open:
                execution_time = now.replace(hour=9, minute=30, second=0, microsecond=0)

            # ⏩ SKIP to Monday if Saturday or Sunday
            while execution_time.weekday() >= 5:
                execution_time += timedelta(days=1)

            await ctx.send(
                f"Market closed. Scheduling {action.upper()} {ticker.upper()} for {execution_time.strftime('%A %m/%d %H:%M')}."
            )
            try:
                if "/" in time:
                    if " " in time:
                        date_part, time_part = time.split(" ")
                        month, day = map(int, date_part.split("/"))
                        hour, minute = map(int, time_part.split(":"))
                        execution_time = now.replace(
                            month=month,
                            day=day,
                            hour=hour,
                            minute=minute,
                            second=0,
                            microsecond=0,
                        )
                    else:
                        month, day = map(int, time.split("/"))
                        execution_time = now.replace(
                            month=month,
                            day=day,
                            hour=9,
                            minute=30,
                            second=0,
                            microsecond=0,
                        )
                else:
                    hour, minute = map(int, time.split(":"))
                    execution_time = now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )

                if execution_time < now:
                    execution_time += timedelta(days=1)

                # ⏩ Also skip weekends if custom-scheduled
                while execution_time.weekday() >= 5:
                    execution_time += timedelta(days=1)

            except ValueError as ve:
                logger.error(
                    f"Invalid time format provided by user: {time}. Error: {ve}"
                )
                await ctx.send(
                    "Invalid time format. Use HH:MM, mm/dd, or HH:MM on mm/dd."
                )
                return

        # Now actually schedule the order
        await schedule_and_execute(
            ctx,
            action=action,
            ticker=ticker,
            quantity=quantity,
            broker=broker,
            execution_time=execution_time,
        )
        logger.info(
            f"Order scheduled: {action.upper()} {ticker.upper()} {quantity} {broker} at {execution_time}."
        )

    except Exception as e:
        logger.error(f"Error scheduling {action} order: {e}")
        await ctx.send(f"An error occurred: {e}")


@bot.command(
    name="liquidate",
    help="Liquidate holdings for a brokerage. Usage: `..liquidate <broker> [test_mode=false]`",
)
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
        logger.info(f"Liquidate position order logged for {broker}")
        await sell_all_position(ctx, broker, test_mode)

    except Exception as e:
        logger.error(f"Error during liquidation: {e}")
        await ctx.send(f"An error occurred: {str(e)}")


@bot.command(name="restart")
async def restart(ctx):
    """Restarts the bot."""
    await ctx.send("\n(・_・ヾ)     (-.-)Zzz...\n")
    await ctx.send(
        "AYO WISEGUY THIS COMMAND IS BROKEN AND WILL BE DISRUPTIVE TO THE DISCORD BOT! NICE WORK GENIUS!"
    )
    logger.debug("The command now works as intended, but I like the message.")
    await asyncio.sleep(1)
    logger.info("Attempting to restart the bot...")
    try:
        python = sys.executable
        os.execv(python, [python] + sys.argv)
    except Exception as e:
        logger.error(f"Error during restart: {e}")
        await ctx.send("An error occurred while attempting to restart the bot.")


@bot.command(name="clear", help="Batch clears excess messages.")
@commands.has_permissions(manage_messages=True)
async def batchclear(ctx, limit: int):
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


@bot.event
async def on_message(message):
    try:
        await handle_on_message(bot, message)
    except Exception as e:
        logger.error(f"Error in on_message handler: {e}")
    await bot.process_commands(message)


async def send_scheduled_reminder():
    """Send scheduled reminders to the target channel."""
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel:
        await send_reminder_message_embed(channel)
    else:
        logger.error(
            f"Could not find channel with ID: {DISCORD_PRIMARY_CHANNEL} to send reminder."
        )


@bot.command(
    name="tosell", help="Usage: `..addsell <ticker>` Add a ticker to the sell list. "
)
async def add_to_sell(ctx, ticker: str):
    """Add a ticker to the sell list."""
    ticker = ticker.upper()
    watch_list_manager.add_to_sell_list(ticker)
    await ctx.send(f"Added {ticker} to the sell list.")


@bot.command(
    name="nosell",
    help="Remove a ticker from the sell list. Usage: `..removesell <ticker>`",
)
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


@bot.command(
    name="bw",
    help="Broker-With <ticker> (details) | All brokers with specified ticker, opt details=specific broker",
)
async def broker_has(ctx, ticker: str, *args):
    """Shows broker-level summary for a specific ticker."""
    specific_broker = args[0] if args else None
    await track_ticker_summary(
        ctx, ticker, show_details=bool(specific_broker), specific_broker=specific_broker
    )


@bot.command(
    name="grouplist", help="Summary by account owner. Optional: specify a broker."
)
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
@bot.command(
    name="top",
    help="Displays the top holdings by dollar value (Quantity <= 1) grouped by broker.",
)
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

    await watch_list_manager.watch_ticker(ctx, ticker, split_date, split_ratio)


@bot.command(
    name="addratio",
    help="Adds or updates the split ratio for an existing ticker in the watchlist.",
)
async def add_ratio(ctx, ticker: str, split_ratio: str):
    if not split_ratio:
        await ctx.send("Please include split ratio: * X-Y *")
        return

    await watch_list_manager.watch_ratio(ctx, ticker, split_ratio)


@bot.command(name="watchlist", help="Lists all tickers currently being watched.")
async def allwatching(ctx):
    """Lists all tickers being watched."""
    await watch_list_manager.list_watched_tickers(ctx)


@bot.command(name="ok", help="watched <ticker> | Removes a ticker from the watchlist.")
async def watched_ticker(ctx, ticker: str):
    """Removes a ticker from the watchlist."""
    await watch_list_manager.stop_watching(ctx, ticker)


@bot.command(name="todiscord", help="Prints text file one line at a time")
async def print_by_line(ctx):
    """Prints contents of a file to Discord, one line at a time."""
    await print_to_discord(ctx)


@bot.command(
    name="addmap",
    help="Usage: addmap <brokerage> <broker_no> <account (last 4)> <Account Nickname> | Adds mapping details for an account to the Account Mappings file.",
)
async def add_account_mappings_command(
    ctx, brokerage: str, broker_no: str, account: str, nickname: str
):
    try:
        # Validate the inputs
        if not (brokerage and broker_no and account and nickname):
            await ctx.send(
                "All arguments are required: `<brokerage> <broker_no> <account> <nickname>`."
            )
            return

        await add_account_mappings(ctx, brokerage, broker_no, account, nickname)
    except Exception as e:
        logger.info(f"An error ocurred: {e}")


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


@bot.command(
    name="clearmap",
    help="Clears all account mappings from the account_mapping.json file",
)
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


@bot.command(name="all", help="Daily reminder with holdings refresh.")
async def show_reminder(ctx):
    """Shows a daily reminder message."""
    await ctx.send("Clearing the current holdings for refresh.")
    await clear_holdings(ctx)
    await send_reminder_message_embed(ctx)


@bot.command(
    name="shutdown",
    help="Gracefully shuts down the bot.",
    brief="Stop the bot",
    category="Admin",
)
async def shutdown(ctx):
    await ctx.send("no you")
    logger.info("Shutdown from main. Deactivating.")
    shutdown_handler(signal.SIGTERM, None)  # Manually call the handler


# Graceful shutdown handler
def shutdown_handler(signal_received, frame):
    logger.info("RSAssistant - shutting down...")
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
