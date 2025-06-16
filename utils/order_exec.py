"""Async order execution helpers for autoRSA interactions."""

import asyncio
import logging

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta

from utils.watch_utils import watch_list_manager

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

async def send_sell_command(ctx, command: str, loop=None):
    """
    Sends the `!rsa sell` command to the specified Discord channel using helperAPI.

    Args:
        ctx (discord.ext.commands.Context): The Discord context object.
        command (str): The command to send.
        loop (asyncio.AbstractEventLoop): The event loop for task queue processing.
    """
    try:
        # Send the command using the helperAPI
        logger.info(f"Preparing to send command: {command}")
        await ctx.send(command)
        logger.info(f"Sent command: {command} to channel {ctx.channel.id}")
    except Exception as e:
        logger.error(f"Error sending sell command: {e}")
        await ctx.send(command)


async def process_sell_list():
    while True:
        try:
            now = datetime.now()
            for ticker, details in list(watch_list_manager.sell_list.items()):
                scheduled_time = datetime.strptime(details["scheduled_time"], "%Y-%m-%d %H:%M:%S")
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



async def schedule_and_execute(ctx, action: str, ticker: str, quantity: float, broker: str, execution_time: datetime):
    """
    Schedules and executes a sell order by sending a command to the target bot using helperAPI.

    Args:
        ctx (discord.ext.commands.Context): The Discord context object.
        action (str): Order type - buy|sell
        ticker (str): The stock ticker symbol.
        quantity (float): Quantity of stock to sell.
        broker (str): Broker to execute the sell order. Use 'all' for all brokers.
        execution_time (datetime): The time to execute the sell order.
    """
    try:
        # Add order to the sell list
        watch_list_manager.add_to_sell_list(
            ticker=ticker,
            broker=broker,
            quantity=quantity,
            scheduled_time=execution_time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Calculate delay until execution
        now = datetime.now()
        delay = (execution_time - now).total_seconds()

        if delay > 0:
            logger.info(f"Waiting {delay} seconds to execute {action} command.")
            await asyncio.sleep(delay)

        # Construct the command
        command = f"!rsa {action} {quantity} {ticker.upper()} {broker} false"

        # Execute the command
        await send_sell_command(ctx, command, loop=asyncio.get_event_loop())

    except Exception as e:
        logger.error(f"Error in scheduled {action} order execution: {e}")
