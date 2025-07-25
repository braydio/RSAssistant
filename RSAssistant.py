# RSAssistant.py
"""Discord bot for monitoring reverse splits and scheduling trades.

This module initializes the Discord bot, registers command handlers, and
manages scheduled orders using a persistent queue.
"""
import asyncio
import json
import os
import signal
import sys
import logging
from datetime import datetime, timedelta

# Third-party imports
import discord
import discord.gateway
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord.ext import commands

# Local utility imports
from utils.logging_setup import setup_logging

from utils.config_utils import (
    BOT_TOKEN,
    DISCORD_PRIMARY_CHANNEL,
    DISCORD_SECONDARY_CHANNEL,
    DISCORD_AI_CHANNEL,
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
from utils.order_exec import schedule_and_execute
from utils.order_queue_manager import (
    get_order_queue,
    list_order_queue,
)
from utils.sql_utils import init_db
from utils.utility_utils import (
    all_account_nicknames,
    all_brokers,
    generate_broker_summary_embed,
    generate_owner_totals_embed,
    print_to_discord,
    track_ticker_summary,
)
from utils.on_message_utils import (
    handle_on_message,
    set_channels,
    enable_audit,
    disable_audit,
    get_audit_summary,
)
from utils.watch_utils import (
    periodic_check,
    send_reminder_message_embed,
    send_reminder_message,
    watch_list_manager,
)

bot_info = (
    "RSAssistant by @braydio \n    <https://github.com/braydio/RSAssistant> \n \n "
)
setup_logging()

logger = logging.getLogger(__name__)

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


async def reschedule_queued_orders():
    """Reschedule any persisted orders from previous runs."""
    queue = get_order_queue()
    if not queue:
        logger.info("No queued orders to reschedule.")
        return

    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if not channel:
        logger.error("Primary channel not found for rescheduling orders.")
        return

    for order_id, data in queue.items():
        try:
            execution_time = datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")
            bot.loop.create_task(
                schedule_and_execute(
                    channel,
                    action=data["action"],
                    ticker=data["ticker"],
                    quantity=data["quantity"],
                    broker=data["broker"],
                    execution_time=execution_time,
                    order_id=order_id,
                    add_to_queue=False,
                )
            )
            logger.info(f"Rescheduled queued order {order_id}")
        except Exception as exc:
            logger.error(f"Failed to reschedule order {order_id}: {exc}")


@bot.event
async def on_ready():
    """Triggered when the bot is ready."""
    global periodic_task
    now = datetime.now()

    logger.info(
        "RSAssistant by @braydio - GitHub: https://github.com/braydio/RSAssistant"
    )
    logger.info("V3.1 | Running in CLI | Runtime Environment: Production")

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

    # Send ready message with current time and queue size
    if channel:
        queued = len(get_order_queue())
        await channel.send(
            f"{ready_message}\nTime: {now.strftime('%Y-%m-%d %H:%M:%S')} | Queued orders: {queued}"
        )
    else:
        logger.warning(
            f"Target channel not found - ID: {DISCORD_PRIMARY_CHANNEL} on startup."
        )
    logger.info("Initializing Application in Production environment.")
    logger.info(
        f"{bot.user} has connected to Discord! PRIMARY | {DISCORD_PRIMARY_CHANNEL}, SECONDARY | {DISCORD_SECONDARY_CHANNEL}, | TERTIARY | {DISCORD_AI_CHANNEL}"
    )
    set_channels(DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL, DISCORD_AI_CHANNEL)

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
            lambda: bot.loop.create_task(send_reminder_message(bot)),
            CronTrigger(hour=8, minute=45),
        )
        reminder_scheduler.add_job(
            lambda: bot.loop.create_task(send_reminder_message(bot)),
            CronTrigger(hour=15, minute=30),
        )
        reminder_scheduler.start()
        logger.info("Scheduled reminders at 8:45 AM and 3:30 PM started.")
    else:
        logger.info("Reminder scheduler already running.")

    await reschedule_queued_orders()


async def process_sell_list(bot):
    """Checks the sell list and executes due sell orders."""
    try:
        now = datetime.now()
        sell_list = watch_list_manager.sell_list

        for ticker, details in list(sell_list.items()):
            scheduled_time = datetime.strptime(
                details["scheduled_time"], "%Y-%m-%d %H:%M:%S"
            )

            if now >= scheduled_time:
                command = f"!rsa sell {details['quantity']} {ticker} {details['broker']} false"
                channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
                if channel:
                    await channel.send(command)
                    logger.info(
                        f"Executed sell order for {ticker} via {details['broker']}"
                    )
                else:
                    logger.warning(
                        f"Primary channel not found when sending sell command for {ticker}."
                    )
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

        def next_open(base: datetime) -> datetime:
            t = base
            if t >= market_close:
                t = (t + timedelta(days=1)).replace(
                    hour=9, minute=30, second=0, microsecond=0
                )
            elif t < market_open:
                t = t.replace(hour=9, minute=30, second=0, microsecond=0)
            while t.weekday() >= 5:
                t += timedelta(days=1)
            return t

        if time:
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
            except ValueError as ve:
                logger.error(
                    f"Invalid time format provided by user: {time}. Error: {ve}"
                )
                await ctx.send(
                    "Invalid time format. Use HH:MM, mm/dd, or HH:MM on mm/dd."
                )
                return
            execution_time = next_open(execution_time)
        else:
            if market_open <= now <= market_close and now.weekday() < 5:
                execution_time = now
            else:
                execution_time = next_open(now)

        if execution_time == now:
            await ctx.send(
                f"Executing {action.upper()} {ticker.upper()} immediately (market open)."
            )
        else:
            await ctx.send(
                f"Scheduling {action.upper()} {ticker.upper()} for {execution_time.strftime('%A %m/%d %H:%M')}"
            )

        order_id = f"{ticker.upper()}_{execution_time.strftime('%Y%m%d_%H%M')}_{action.lower()}"
        bot.loop.create_task(
            schedule_and_execute(
                ctx,
                action=action,
                ticker=ticker,
                quantity=quantity,
                broker=broker,
                execution_time=execution_time,
                order_id=order_id,
            )
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
    if message.content.startswith(".."):
        logger.info(f"Handling command {message.content}")
        await bot.process_commands(message)
    else:
        await handle_on_message(bot, message)


async def send_scheduled_reminder():
    """Send scheduled reminders to the target channel."""
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel:
        await send_reminder_message_embed(channel)
    else:
        logger.error(
            f"Could not find channel with ID: {DISCORD_PRIMARY_CHANNEL} to send reminder."
        )


@bot.command(name="selling", help="View the current sell queue.")
async def view_sell_list(ctx):
    sell_list = watch_list_manager.get_sell_list()
    if not sell_list:
        await ctx.send("The sell list is empty.")
    else:
        logger.info("User requested view of sell list.")
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
    embed = generate_broker_summary_embed(broker)
    await ctx.send(
        embed=(
            embed if embed else "An error occurred while generating the broker summary."
        )
    )


@bot.command(
    name="ownersummary",
    help="Shows total holdings for each owner across all brokers.",
)
async def owner_summary(ctx):
    """Display aggregated owner holdings across all brokers."""
    embed = generate_owner_totals_embed()
    await ctx.send(embed=embed)


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
    """Refresh holdings and report watchlist gaps.

    This command clears existing holdings, posts a watchlist reminder,
    triggers a holdings refresh via AutoRSA, and audits each account's
    holdings against the watchlist as the data is received. After all
    brokers complete, a summary of missing tickers is posted before the
    regular broker summary for each watchlist ticker.
    """
    await ctx.send("Clearing the current holdings for refresh.")
    await clear_holdings(ctx)
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel:
        await send_reminder_message_embed(channel)
        enable_audit()
        await ctx.send("!rsa holdings all")

        def check(message: discord.Message) -> bool:
            return (
                message.channel == ctx.channel
                and "All commands complete in all brokers" in message.content
            )

        try:
            await bot.wait_for("message", check=check, timeout=600)
            summary = get_audit_summary()
            disable_audit()
            if summary:
                embed = discord.Embed(
                    title="Missing Watchlist Holdings",
                    color=discord.Color.red(),
                )
                for account, tickers in summary.items():
                    embed.add_field(
                        name=account,
                        value=", ".join(tickers),
                        inline=False,
                    )
                await ctx.send(embed=embed)
            watch_list = watch_list_manager.get_watch_list()
            for ticker in watch_list.keys():
                await ctx.invoke(broker_has, ticker=ticker)
        except asyncio.TimeoutError:
            disable_audit()
            await ctx.send("Timed out waiting for AutoRSA response.")


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


# Shutdown handler
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
