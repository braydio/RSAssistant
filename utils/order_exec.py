"""Async order execution helpers for autoRSA interactions."""

import asyncio
import logging
import time
from datetime import datetime

from utils.watch_utils import watch_list_manager
from utils.channel_resolver import resolve_reply_channel
from utils.config_utils import (
    DISCORD_PRIMARY_CHANNEL,
    RSA_COMMAND_MIN_INTERVAL_SECONDS,
)
from utils.order_queue_manager import add_to_order_queue, remove_order
from utils.market_calendar import MARKET_TZ, is_market_open_at, next_market_open

logger = logging.getLogger(__name__)

# Task queue for handling messages
task_queue = asyncio.Queue()
_rsa_command_lock = asyncio.Lock()
_last_rsa_command_at = 0.0
_ORDER_COMMANDS = {"buy", "sell"}


async def _await_rsa_rate_limit() -> None:
    """Enforce a minimum interval between !rsa command sends."""
    global _last_rsa_command_at
    async with _rsa_command_lock:
        now = time.monotonic()
        elapsed = now - _last_rsa_command_at
        delay = max(0.0, RSA_COMMAND_MIN_INTERVAL_SECONDS - elapsed)
        if delay > 0:
            logger.info("Rate limiting !rsa command for %.2fs.", delay)
            await asyncio.sleep(delay)
        _last_rsa_command_at = time.monotonic()


async def _schedule_closed_market_order(target_channel, command: str, bot=None) -> bool:
    """Schedule !rsa order commands if the market is currently closed."""

    text = command.strip()
    parts = text.split()
    if len(parts) < 2:
        return False

    action = parts[1].lower()
    if action not in _ORDER_COMMANDS:
        return False

    now = datetime.now(MARKET_TZ)
    if is_market_open_at(now):
        return False

    if len(parts) < 4:
        await target_channel.send(
            "Market is closed. Unable to parse the order details; please retry when markets reopen."
        )
        logger.warning(
            "Closed-market order missing arguments, skipping send: %s", command
        )
        return True

    quantity_str = parts[2]
    ticker = parts[3]
    broker = parts[4] if len(parts) > 4 else "all"

    try:
        quantity = float(quantity_str)
    except ValueError:
        await target_channel.send(
            "Market is closed. Unable to interpret the order quantity; please retry when markets reopen."
        )
        logger.warning(
            "Closed-market order has invalid quantity, skipping send: %s", command
        )
        return True

    execution_time = next_market_open(now)
    scheduled_label = execution_time.strftime("%H:%M on %A %m/%d")
    await target_channel.send(
        f"Market is closed. Scheduling {text} for {scheduled_label}."
    )
    logger.info(
        "Market closed – scheduling command %s for %s.",
        text,
        scheduled_label,
    )

    order_id = f"{ticker.upper()}_{execution_time.strftime('%Y%m%d_%H%M')}_{action}"
    loop = asyncio.get_running_loop()
    loop.create_task(
        schedule_and_execute(
            target_channel,
            action=action,
            ticker=ticker,
            quantity=quantity,
            broker=broker,
            execution_time=execution_time,
            bot=bot,
            order_id=order_id,
        )
    )
    return True


async def processTasks(message):
    """
    Processes the task queue and sends messages (mock implementation).

    Args:
        message (str): The message to be sent to Discord.
    """
    logger.info(f"Sending message to Discord: {message}")
    # Simulate sending a message to Discord here
    await asyncio.sleep(0.1)  # Mock delay for sending the message


def printAndDiscord(message, loop=None):
    """
    Adds a message to the task queue and sends it using an event loop.

    Args:
        message (str): The message to send to Discord.
        loop (asyncio.AbstractEventLoop): The event loop for task queue processing.
    """
    logger.info(message)
    if loop:
        loop.call_soon_threadsafe(task_queue.put_nowait, message)
        if task_queue.qsize() == 1:  # Start processing if the queue is not empty
            asyncio.run_coroutine_threadsafe(processQueue(), loop)


async def processQueue():
    """
    Processes all tasks in the queue and sends them to Discord.
    """
    while not task_queue.empty():
        message = await task_queue.get()
        await processTasks(message)
        task_queue.task_done()


async def send_sell_command(target, command: str, loop=None, bot=None):
    """Send an order command to the configured primary channel when possible."""

    try:
        logger.info(f"Preparing to send command: {command}")
        primary_channel = None
        if bot is not None:
            primary_channel = resolve_reply_channel(
                bot, preferred_id=DISCORD_PRIMARY_CHANNEL
            )
        target_channel = primary_channel or target
        if target_channel is None:
            logger.error("No channel available to send order command.")
            return
        resolved_bot = bot or getattr(target_channel, "bot", None)
        if command.strip().lower().startswith("!rsa"):
            if await _schedule_closed_market_order(
                target_channel, command, resolved_bot
            ):
                return
            await _await_rsa_rate_limit()
        await target_channel.send(command)
        channel = getattr(target_channel, "channel", target_channel)
        channel_id = getattr(channel, "id", "unknown")
        logger.info(f"Sent command: {command} to channel {channel_id}")
    except Exception as e:
        logger.error(f"Error sending sell command: {e}")


async def process_sell_list():
    while True:
        try:
            now = datetime.now(MARKET_TZ)
            for ticker, details in list(watch_list_manager.sell_list.items()):
                scheduled_time = datetime.strptime(
                    details["scheduled_time"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=MARKET_TZ)
                if now >= scheduled_time and is_market_open_at(now):
                    # Execute the sell command
                    command = f"test command {details['quantity']} {ticker} {details['broker']} false"
                    await send_sell_command(None, command)

                    # Remove the executed order from the sell list
                    del watch_list_manager.sell_list[ticker]
                    watch_list_manager.save_sell_list()
                    logger.info(f"Executed and removed {ticker} from sell list.")
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error processing sell list: {e}")


async def schedule_and_execute(
    ctx,
    action: str,
    ticker: str,
    quantity: float,
    broker: str,
    execution_time: datetime,
    bot=None,
    *,
    order_id: str | None = None,
    add_to_queue: bool = True,
):
    """Schedule and execute an order at ``execution_time``."""

    try:
        if order_id is None:
            order_id = f"{ticker.upper()}_{execution_time.strftime('%Y%m%d_%H%M')}_{action.lower()}"

        if add_to_queue:
            add_to_order_queue(
                order_id,
                {
                    "action": action,
                    "ticker": ticker.upper(),
                    "quantity": quantity,
                    "broker": broker,
                    "time": execution_time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

        if action.lower() == "sell":
            watch_list_manager.add_to_sell_list(
                ticker=ticker,
                broker=broker,
                quantity=quantity,
                scheduled_time=execution_time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        now = datetime.now(MARKET_TZ)
        if execution_time.tzinfo is None:
            execution_time = execution_time.replace(tzinfo=MARKET_TZ)
        reference_time = execution_time if execution_time > now else now
        if not is_market_open_at(reference_time):
            execution_time = next_market_open(reference_time)

        delay = max((execution_time - now).total_seconds(), 0)
        if delay > 0:
            logger.info(
                "Waiting %.0f seconds to execute %s command (scheduled for %s).",
                delay,
                action,
                execution_time,
            )
            await asyncio.sleep(delay)

        command = f"!rsa {action} {quantity} {ticker.upper()} {broker} false"
        resolved_bot = bot or getattr(ctx, "bot", None)
        await send_sell_command(
            ctx, command, loop=asyncio.get_event_loop(), bot=resolved_bot
        )

        if action.lower() == "sell":
            watch_list_manager.remove_from_sell_list(ticker)

        remove_order(order_id)

    except Exception as e:
        logger.error(f"Error in scheduled {action} order execution: {e}")
