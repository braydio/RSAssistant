"""Async order execution helpers for autoRSA interactions."""

import asyncio
import logging
from datetime import datetime, timedelta

from utils.watch_utils import watch_list_manager
from utils.order_queue_manager import add_to_order_queue, remove_order

logger = logging.getLogger(__name__)

# Task queue for handling messages
task_queue = asyncio.Queue()


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


async def send_sell_command(target, command: str, loop=None):
    """Send an order command to a Discord context or channel."""

    try:
        logger.info(f"Preparing to send command: {command}")
        await target.send(command)
        channel = getattr(target, "channel", target)
        channel_id = getattr(channel, "id", "unknown")
        logger.info(f"Sent command: {command} to channel {channel_id}")
    except Exception as e:
        logger.error(f"Error sending sell command: {e}")


async def process_sell_list():
    while True:
        try:
            now = datetime.now()
            for ticker, details in list(watch_list_manager.sell_list.items()):
                scheduled_time = datetime.strptime(
                    details["scheduled_time"], "%Y-%m-%d %H:%M:%S"
                )
                if now >= scheduled_time:
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

        now = datetime.now()
        delay = max((execution_time - now).total_seconds(), 0)
        if delay > 0:
            logger.info(f"Waiting {delay} seconds to execute {action} command.")
            await asyncio.sleep(delay)

        command = f"!rsa {action} {quantity} {ticker.upper()} {broker} false"
        await send_sell_command(ctx, command, loop=asyncio.get_event_loop())

        if action.lower() == "sell":
            watch_list_manager.remove_from_sell_list(ticker)

        remove_order(order_id)

    except Exception as e:
        logger.error(f"Error in scheduled {action} order execution: {e}")
