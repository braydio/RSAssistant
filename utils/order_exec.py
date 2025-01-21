import logging
import asyncio
from datetime import datetime, timedelta

# Task queue for handling messages
task_queue = asyncio.Queue()

async def processTasks(message):
    """
    Processes the task queue and sends messages (mock implementation).

    Args:
        message (str): The message to be sent to Discord.
    """
    print(f"Sending message to Discord: {message}")
    # Simulate sending a message to Discord here
    await asyncio.sleep(0.1)  # Mock delay for sending the message

def printAndDiscord(message, loop=None):
    """
    Adds a message to the task queue and sends it using an event loop.

    Args:
        message (str): The message to send to Discord.
        loop (asyncio.AbstractEventLoop): The event loop for task queue processing.
    """
    print(message)  # Log to console
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
        logging.info(f"Preparing to send command: {command}")
        printAndDiscord(command, loop=loop)
        logging.info(f"Sent command: {command} to channel {ctx.channel.id}")
    except Exception as e:
        logging.error(f"Error sending sell command: {e}")
        await ctx.send(command)


async def schedule_and_execute(ctx, action: str, ticker: str, quantity: float, broker: str, dry_mode: str, execution_time: datetime):
    """
    Schedules and executes a sell order by sending a command to the target bot using helperAPI.

    Args:
        ctx (discord.ext.commands.Context): The Discord context object.
        action (str): Order type - buy|sell
        ticker (str): The stock ticker symbol.
        quantity (float): Quantity of stock to sell.
        broker (str): Broker to execute the sell order. Use 'all' for all brokers.
        dry_mode (str): "true" for simulation, "false" for live.
        execution_time (datetime): The time to execute the sell order.
    """
    try:
        # Delay until the specified execution time
        now = datetime.now()
        delay = (execution_time - now).total_seconds()

        if delay > 0:
            logging.info(f"Waiting {delay} seconds to execute sell command.")
            await asyncio.sleep(delay)

        # Construct the sell command
        command = f"!rsa {action} {quantity} {ticker.upper()} {broker} {dry_mode.lower()}"

        # Send the command
        await send_sell_command(ctx, command, loop=asyncio.get_event_loop())

    except Exception as e:
        logging.error(f"Error in scheduled sell order execution: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Example parameters for testing purposes
    class MockContext:
        """Mock context for testing purposes."""
        async def send(self, message):
            print(f"Mock send: {message}")
        
        @property
        def channel(self):
            return type("MockChannel", (object,), {"id": 12345})()

    ctx = MockContext()
    ticker = "AAPL"
    quantity = 10
    broker = "chase"
    dry_mode = "false"
    execution_time = datetime.now() + timedelta(seconds=30)  # 30 seconds from now

    # Running the test with a mock context
    asyncio.run(schedule_and_execute(ctx, ticker, quantity, broker, dry_mode, execution_time))
