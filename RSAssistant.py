# RSAssistant.py
"""Discord bot for monitoring reverse splits and scheduling trades.

This module initializes the Discord bot, registers command handlers, and
manages scheduled orders using a persistent queue. Commands are grouped by
category and served through a custom help formatter so ``..help`` displays
usage details.
"""

import asyncio
import json
import os
import signal
import sys
import logging
from datetime import datetime, timedelta
import itertools

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
    DISCORD_TERTIARY_CHANNEL,
    EXCEL_FILE_MAIN,
    HOLDINGS_LOG_CSV,
    ORDERS_LOG_CSV,
    ACCOUNT_MAPPING,
    BOT_PREFIX,
    SQL_LOGGING_ENABLED,
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
    watch as handle_watch_command,
)
from utils.refresh_scheduler import compute_next_refresh_datetime, MARKET_TZ

bot_info = (
    "RSAssistant by @braydio \n    <https://github.com/braydio/RSAssistant> \n \n "
)
setup_logging()

logger = logging.getLogger(__name__)

if SQL_LOGGING_ENABLED:
    init_db()
else:
    logger.info("SQL logging disabled; skipping database initialization.")

logger.info(f"Holdings Log CSV file: {HOLDINGS_LOG_CSV}")
logger.info(f"Orders Log CSV file: {ORDERS_LOG_CSV}")


class CategoryHelpCommand(commands.MinimalHelpCommand):
    """Custom help command grouping commands by category."""

    def get_category(self, command: commands.Command) -> str:
        return command.extras.get("category", self.no_category)

    async def send_bot_help(self, mapping):
        """Show grouped help for all commands."""
        bot = self.context.bot
        note = self.get_opening_note()
        if note:
            self.paginator.add_line(note, empty=True)

        filtered = await self.filter_commands(
            bot.commands, sort=True, key=self.get_category
        )
        for category, commands_iter in itertools.groupby(
            filtered, key=self.get_category
        ):
            self.paginator.add_line(f"__**{category}**__")
            for command in commands_iter:
                self.add_command_formatting(command)
            self.paginator.add_line()

        await self.send_pages()

    async def send_command_help(self, command):
        """Show detailed help for a single command."""
        category = self.get_category(command)
        self.paginator.add_line(f"__**Category:** {category}__", empty=True)
        self.add_command_formatting(command)
        await self.send_pages()


# Set up bot intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True


discord.gateway.DiscordWebSocket.resume_timeout = 60  # seconds
discord.gateway.DiscordWebSocket.gateway_timeout = 60  # seconds

# Initialize bot
bot = commands.Bot(
    command_prefix=BOT_PREFIX, case_insensitive=True, intents=intents, reconnect=True
)
bot.help_command = CategoryHelpCommand()

periodic_task = None
reminder_scheduler = None
total_refresh_task = None
_total_refresh_lock = asyncio.Lock()


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


async def _invoke_total_refresh(bot: commands.Bot) -> None:
    """Trigger the ``..all`` command from the scheduler context."""

    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel is None:
        logger.error(
            "Total refresh scheduler could not resolve primary channel %s",
            DISCORD_PRIMARY_CHANNEL,
        )
        return

    command = bot.get_command("all")
    if command is None:
        logger.error("Total refresh scheduler could not locate '..all' command handler")
        return

    message = await channel.send(f"{BOT_PREFIX}all")
    try:
        ctx = await bot.get_context(message)
        await bot.invoke(ctx)
    finally:
        try:
            await message.delete()
        except discord.HTTPException as exc:
            logger.debug(f"Unable to delete scheduled '..all' trigger message: {exc}")


async def _execute_total_refresh(bot: commands.Bot) -> None:
    """Execute the scheduled ``..all`` refresh with locking."""

    if _total_refresh_lock.locked():
        logger.warning("Skipping scheduled '..all' refresh; previous run still active.")
        return

    async with _total_refresh_lock:
        logger.info("Executing scheduled '..all' holdings refresh.")
        await _invoke_total_refresh(bot)


async def run_total_refresh_scheduler(bot: commands.Bot) -> None:
    """Invoke ``..all`` at a cadence matching market and off-hours policies."""

    while True:
        now = datetime.now(MARKET_TZ)
        next_run = compute_next_refresh_datetime(now)
        wait_seconds = max((next_run - now).total_seconds(), 0)
        logger.info(
            "Next scheduled '..all' refresh at %s",
            next_run.astimezone(MARKET_TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
        )
        try:
            await asyncio.sleep(wait_seconds)
        except asyncio.CancelledError:
            logger.info("Total refresh scheduler cancelled before next execution.")
            raise

        try:
            await _execute_total_refresh(bot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception(f"Scheduled '..all' refresh failed: {exc}")

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
            else "Watching for order activity o.O"
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
        f"{bot.user} has connected to Discord! PRIMARY | {DISCORD_PRIMARY_CHANNEL}, SECONDARY | {DISCORD_SECONDARY_CHANNEL}, | TERTIARY | {DISCORD_TERTIARY_CHANNEL}"
    )
    set_channels(
        DISCORD_PRIMARY_CHANNEL, DISCORD_SECONDARY_CHANNEL, DISCORD_TERTIARY_CHANNEL
    )

    # Check if the periodic task is already running, and start it if not
    if "periodic_task" not in globals() or periodic_task is None:
        periodic_task = asyncio.create_task(periodic_check(bot))
        logger.info("Periodic check task started.")
    else:
        logger.info("Periodic check task is already running.")

    global total_refresh_task
    if total_refresh_task is None:
        total_refresh_task = asyncio.create_task(run_total_refresh_scheduler(bot))
        logger.info("Total refresh scheduler started.")
    else:
        logger.info("Total refresh scheduler already running.")

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


@bot.command(
    name="queue",
    help="View all scheduled orders.",
    usage="",
    extras={"category": "Orders"},
)
async def show_order_queue(ctx):
    queue = list_order_queue()
    if not queue:
        await ctx.send("There are no scheduled orders.")
    else:
        message = "**Scheduled Orders:**\n" + "\n".join(queue)
        await ctx.send(message)


ORD_COMMAND_USAGE = (
    f"{BOT_PREFIX}ord <buy/sell> <ticker> [broker] [quantity] [time]"
)


@bot.command(
    name="ord",
    help="Schedule a buy or sell order.",
    usage="<buy/sell> <ticker> [broker] [quantity] [time]",
    extras={"category": "Orders"},
)
async def process_order(
    ctx,
    action: str,
    ticker: str = None,
    broker: str = "all",
    quantity: float = 1,
    time: str = None,
):
    """Validate input and schedule an order for execution."""

    invalid_usage_message = (
        f"Invalid arguments. Expected format: `{ORD_COMMAND_USAGE}`"
    )

    if not action or action.lower() not in {"buy", "sell"}:
        await ctx.send(invalid_usage_message)
        return

    if not ticker:
        await ctx.send(invalid_usage_message)
        return

    try:
        quantity_value = float(quantity)
    except (TypeError, ValueError):
        await ctx.send(invalid_usage_message)
        return

    if quantity_value <= 0:
        await ctx.send(invalid_usage_message)
        return

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
                quantity=quantity_value,
                broker=broker,
                execution_time=execution_time,
                order_id=order_id,
            )
        )
        logger.info(
            f"Order scheduled: {action.upper()} {ticker.upper()} {quantity_value} {broker} at {execution_time}."
        )

    except Exception as e:
        logger.error(f"Error scheduling {action} order: {e}")
        await ctx.send(f"An error occurred: {e}")


@process_order.error
async def process_order_error(ctx, error):
    """Provide a helpful usage hint when ``..ord`` fails due to bad input."""

    expected_usage = f"`{ORD_COMMAND_USAGE}`"
    if isinstance(
        error,
        (
            commands.MissingRequiredArgument,
            commands.BadArgument,
            commands.BadUnionArgument,
        ),
    ):
        await ctx.send(f"Invalid arguments. Expected format: {expected_usage}")
        return

    logger.exception("Unexpected error during ..ord execution")
    await ctx.send(f"An error occurred: {error}")


@bot.command(
    name="liquidate",
    help="Liquidate holdings for a brokerage.",
    usage="<broker> [test_mode]",
    extras={"category": "Orders"},
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


@bot.command(name="restart", extras={"category": "Admin"})
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


@bot.command(
    name="clear",
    help="Batch clears excess messages.",
    usage="<limit>",
    extras={"category": "Admin"},
)
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
    if message.author == bot.user:
        logger.info(f"Message is from myself! {bot.user}")
        return
    elif message.content.startswith(BOT_PREFIX):
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


@bot.command(
    name="selling",
    help="View the current sell queue.",
    usage="",
    extras={"category": "Watchlist"},
)
async def view_sell_list(ctx):
    """Display queued sell orders stored by the bot.

    Args:
        ctx (commands.Context): Invocation context for the command.
    """

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


@bot.command(
    name="unsell",
    help="Remove a ticker from the sell queue.",
    usage="<ticker>",
    extras={"category": "Watchlist"},
)
async def remove_sell_order(ctx, ticker: str):
    """Remove a queued sell order for ``ticker`` from the sell list.

    Args:
        ctx (commands.Context): Invocation context for the command.
        ticker (str): Symbol to remove from the sell queue.
    """

    normalized_ticker = ticker.upper()
    removed = watch_list_manager.remove_from_sell_list(normalized_ticker)

    if removed:
        logger.info("Removed %s from sell list via command.", normalized_ticker)
        await ctx.send(f"{normalized_ticker} removed from the sell list.")
    else:
        logger.info(
            "Attempted to remove %s from sell list but it was not present.",
            normalized_ticker,
        )
        await ctx.send(f"{normalized_ticker} was not found in the sell list.")


@bot.command(
    name="brokerlist",
    help="List all active brokers or accounts for a broker.",
    usage="[broker]",
    extras={"category": "Accounts"},
)
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
    help="Show which brokers hold a given ticker.",
    usage="<ticker> [broker]",
    extras={"category": "Reporting"},
    aliases=["brokerwith"],
)
async def broker_has(ctx, ticker: str, *args):
    """Shows broker-level summary for a specific ticker.

    This command is available as ``..bw`` or ``..brokerwith`` and
    optionally accepts a broker name to display account-level details.
    """
    specific_broker = args[0] if args else None
    await track_ticker_summary(
        ctx, ticker, show_details=bool(specific_broker), specific_broker=specific_broker
    )


@bot.command(
    name="grouplist",
    help="Summary by account owner.",
    usage="[broker]",
    extras={"category": "Reporting"},
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
    extras={"category": "Reporting"},
)
async def owner_summary(ctx):
    """Display aggregated owner holdings across all brokers."""
    embed = generate_owner_totals_embed()
    await ctx.send(embed=embed)


# Discord bot command
@bot.command(
    name="top",
    help="Displays the top holdings grouped by broker.",
    usage="[range]",
    extras={"category": "Reporting"},
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
    help="Add ticker(s) to the watchlist.",
    usage="<ticker> <split_date> [split_ratio] | <ticker ratio (purchase by mm/dd)>",
    extras={"category": "Watchlist"},
)
async def watch(ctx, *, text: str):
    """Add one or more tickers to the watchlist.

    The command now supports two input styles:

    * ``..watch TICKER mm/dd [ratio]`` – the traditional single-entry format.
    * ``..watch`` followed by one or more lines using the bulk format,
      e.g. ``TICKER 1-10 (purchase by 10/24)``.
    """

    await handle_watch_command(ctx, text=text)


@bot.command(
    name="addratio",
    help="Add or update the split ratio for a watched ticker.",
    usage="<ticker> <split_ratio>",
    extras={"category": "Watchlist"},
)
async def add_ratio(ctx, ticker: str, split_ratio: str):
    if not split_ratio:
        await ctx.send("Please include split ratio: * X-Y *")
        return

    await watch_list_manager.watch_ratio(ctx, ticker, split_ratio)


@bot.command(
    name="watchlist",
    help="List all tickers currently being watched.",
    extras={"category": "Watchlist"},
)
async def allwatching(ctx):
    """List watched tickers with split dates and ratios."""
    await watch_list_manager.list_watched_tickers(ctx, include_prices=False)


@bot.command(
    name="watchprices",
    help="List watched tickers with split info and latest prices.",
    extras={"category": "Watchlist"},
)
async def watchlist_with_prices(ctx):
    """List watched tickers including their latest price."""
    await watch_list_manager.list_watched_tickers(ctx, include_prices=True)


@bot.command(
    name="prices",
    help="Show the latest price for each watchlist ticker.",
    extras={"category": "Watchlist"},
)
async def watchlist_prices(ctx):
    """Display only the latest prices for watchlist tickers."""
    await watch_list_manager.send_watchlist_prices(ctx)


@bot.command(
    name="ok",
    help="Remove a ticker from the watchlist.",
    usage="<ticker>",
    extras={"category": "Watchlist"},
)
async def watched_ticker(ctx, ticker: str):
    """Removes a ticker from the watchlist."""
    await watch_list_manager.stop_watching(ctx, ticker)


@bot.command(
    name="todiscord",
    help="Print a text file to Discord one line at a time.",
    extras={"category": "Utilities"},
)
async def print_by_line(ctx):
    """Prints contents of a file to Discord, one line at a time."""
    await print_to_discord(ctx)


@bot.command(
    name="addmap",
    help="Add account mapping details.",
    usage="<brokerage> <broker_no> <account> <nickname>",
    extras={"category": "Accounts"},
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


@bot.command(
    name="loadmap",
    help="Map account details from Excel to JSON.",
    extras={"category": "Accounts"},
)
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


@bot.command(
    name="loadlog",
    help="Update Excel log with mapped accounts.",
    extras={"category": "Accounts"},
)
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
    help="Remove all saved account mappings.",
    extras={"category": "Accounts"},
)
async def clear_mapping_command(ctx):
    """Clears all account mappings from the JSON file."""
    try:
        await ctx.send("Clearing account mappings...")
        await clear_account_mappings(ctx)
        await ctx.send("Account mappings have been cleared.")
    except Exception as e:
        await ctx.send(f"An error occurred during the clearing process: {str(e)}")


@bot.command(
    name="clearholdings",
    help="Clear entries in holdings_log.csv",
    extras={"category": "Admin"},
)
async def clear_holdings(ctx):
    """Clears all holdings from the CSV file."""
    success, message = clear_holdings_log(HOLDINGS_LOG_CSV)
    await ctx.send(message if success else f"Failed to clear holdings log: {message}")


@bot.command(
    name="all",
    help="Daily reminder with holdings refresh.",
    extras={"category": "Reporting"},
)
async def show_reminder(ctx):
    """Refresh holdings and report watchlist gaps.

    This command clears existing holdings, posts a watchlist reminder,
    triggers a holdings refresh via AutoRSA, and audits each account's
    holdings against the watchlist as the data is received. After all
    brokers complete, a summary of missing tickers is posted followed by
    a single embed consolidating broker holdings status for each
    watchlist ticker.
    """
    await ctx.send("Clearing the current holdings for refresh.")
    await clear_holdings(ctx)
    channel = bot.get_channel(DISCORD_PRIMARY_CHANNEL)
    if channel:
        await send_reminder_message_embed(channel)
        enable_audit()
        await ctx.send("!rsa holdings all")

        def check(message: discord.Message) -> bool:
            """Return True when AutoRSA signals holdings completion.

            Accepts messages from bots as well as messages authored by
            ``auto-rsa`` to support CLI environments where the AutoRSA
            user may not be flagged as a bot.
            """
            author_ok = message.author.bot or message.author.name.lower() == "auto-rsa"
            return (
                message.channel == ctx.channel
                and author_ok
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
            results = []
            last_timestamp = ""
            for ticker in watch_list.keys():
                statuses, ts = await track_ticker_summary(ctx, ticker, collect=True)
                results.append((ticker, statuses))
                last_timestamp = ts
            summary_embed = discord.Embed(
                title="Broker Holdings Check", color=discord.Color.blue()
            )
            for ticker, statuses in results:
                lines = [
                    f"{broker} {icon} {held}/{total}"
                    for broker, (icon, held, total) in statuses.items()
                ]
                summary_embed.add_field(
                    name=ticker, value="\n".join(lines) or "No data", inline=False
                )
            if last_timestamp:
                summary_embed.set_footer(text=f"Holdings snapshot • {last_timestamp}")
            await ctx.send(embed=summary_embed)
        except asyncio.TimeoutError:
            disable_audit()
            await ctx.send("Timed out waiting for AutoRSA response.")


@bot.command(
    name="shutdown",
    help="Gracefully shuts down the bot.",
    extras={"category": "Admin"},
)
async def shutdown(ctx):
    await ctx.send("no you")
    logger.info("Shutdown from main. Deactivating.")
    shutdown_handler(signal.SIGTERM, None)  # Manually call the handler


# Shutdown handler
def shutdown_handler(signal_received, frame):
    logger.info("RSAssistant - shutting down...")
    global periodic_task, reminder_scheduler, total_refresh_task
    if periodic_task and not periodic_task.done():
        periodic_task.cancel()
    if total_refresh_task and not total_refresh_task.done():
        total_refresh_task.cancel()
    if reminder_scheduler:
        reminder_scheduler.shutdown()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# Start the bot with the token from the .env
if __name__ == "__main__":
    bot.run(BOT_TOKEN)
