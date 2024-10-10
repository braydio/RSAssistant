import json
import os
import logging
import pandas as pd
import discord
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from utils.config_utils import load_config, get_account_nickname, load_account_mappings
from utils.excel_utils import add_stock_to_excel_log
from utils.utility_utils import send_large_message_chunks

# Load configuration and paths from settings
config = load_config()
WATCH_FILE = config['paths']['watch_list']
EXCEL_XLSX_FILE = config['paths']['excel_log']
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
TARGET_CHANNEL_ID = config['discord_ids']['channel_id']  # change to ['discord_ids']['reminder_channel_id']
excluded_brokers = config.get('excluded_brokers', {})

# Dictionary to track the watch list for specific tickers across accounts
watch_list = defaultdict(lambda: defaultdict(dict))

# Helper functions
def save_watch_list():
    """Save the current watch list to a JSON file."""
    with open(WATCH_FILE, 'w') as file:
        json.dump(watch_list, file, default=str)
    logging.info("Watch list saved.")

def load_watch_list():
    """Load the watch list from a JSON file."""
    global watch_list
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE, 'r') as file:
            watch_list.update(json.load(file))
        logging.info("Watch list loaded.")
    else:
        logging.info("No watch list file found, starting fresh.")

def update_watchlist_with_stock(ticker):
    """Adds a stock ticker to the Excel log."""
    ticker = ticker.upper()
    try:
        
        logging.info(f"Successfully added {ticker} to the watchlist and Excel log.")
    except Exception as e:
        logging.error(f"Error updating watchlist: {e}")

# Main functions
async def watch_ticker(ctx, ticker: str, split_date: str):
    """Add a stock ticker with a split date to the watch list."""
    ticker = ticker.upper()
    
    if ticker not in watch_list:
        watch_list[ticker] = {
            'split_date': split_date,
            'reminder_sent': False,
            'brokers': defaultdict(lambda: {
                'state': 'initial',  
                'last_updated': None
            })
        }
        add_stock_to_excel_log(ticker, EXCEL_XLSX_FILE)
        logging.info("Added stock to watchlist and passed to excel utils.")
    await ctx.send(f"Watching {ticker} with a reverse split date on {split_date}.")
    save_watch_list()

def update_watchlist(broker_name, account_nickname, stock, quantity, order_type=None):
    """Updates the watchlist based on holdings data and order type."""
    stock = stock.upper()
    quantity = float(quantity)
    if stock in watch_list:
        watchlist_entry = watch_list[stock]

        if broker_name not in watchlist_entry['brokers']:
            watchlist_entry['brokers'][broker_name] = {}

        if quantity > 0:
            # If the account has a positive quantity, mark it as "has position"
            watchlist_entry['brokers'][broker_name][account_nickname] = {
                'state': 'has position',
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        elif order_type == 'sell':
            # If it's a sell order, mark it as "completed"
            watchlist_entry['brokers'][broker_name][account_nickname] = {
                'state': 'completed',  # Marking as completed instead of removing
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            print(f"Account {account_nickname} marked as completed for {stock}.")
        elif order_type == 'finalize_closure':
            # If we are finalizing the closure, remove the account from the watchlist
            if account_nickname in watchlist_entry['brokers'][broker_name]:
                del watchlist_entry['brokers'][broker_name][account_nickname]
                print(f"Account {account_nickname} closed out position for {stock}.")

            if not watchlist_entry['brokers'][broker_name]:
                del watchlist_entry['brokers'][broker_name]
                print(f"Broker {broker_name} removed from watchlist for {stock}.")

            if not watchlist_entry['brokers']:
                del watch_list[stock]
                print(f"Stock {stock} fully closed across all accounts. Removed from watchlist.")

        save_watch_list()

    else:
        print(f"{stock} is not in the watchlist.")

def should_skip(broker, account_nickname):
    """Returns True if the broker and account_nickname should be skipped."""
    if broker in excluded_brokers and account_nickname in excluded_brokers[broker]:
        return True
    return False

async def check_watchlist_positions(ctx, show_accounts=False):
    """Check which brokers or accounts still need to purchase watchlist tickers."""
    today = datetime.now().strftime('%Y-%m-%d')
    account_mapping = load_account_mappings()

    reminders = []  # Store reminder messages
    for ticker, data in watch_list.items():
        split_date = data.get('split_date')
        split_date = datetime.strptime(split_date, '%m/%d').replace(year=datetime.now().year).strftime('%Y-%m-%d')

        if split_date >= today:
            ticker_reminders = []  # Stores details per ticker
            print(f"Checking ticker {ticker} with split date {split_date}")

            for broker, accounts in account_mapping.items():
                watchlist_broker_accounts = data.get('brokers', {}).get(broker, {})
                print(f"Broker in watchlist: {broker}, Accounts in watchlist for broker: {watchlist_broker_accounts}")

                account_reminders = []
                for account in accounts:
                    account_nickname = get_account_nickname(broker, account)

                    # Skip accounts in the excluded list or completed state
                    if should_skip(broker, account_nickname):
                        continue

                    account_data = watchlist_broker_accounts.get(account_nickname, {})
                    account_state = account_data.get('state', 'waiting')

                    # Only add to reminders if the state is "waiting" or "has position"
                    if account_state == 'waiting' or account_state == 'has position':
                        account_reminders.append(account_nickname)

                if account_reminders:
                    if show_accounts:
                        account_list = ", ".join(account_reminders)
                        ticker_reminders.append(f"Broker: {broker} | Accounts: {account_list}")
                    else:
                        ticker_reminders.append(f"Broker: {broker}")

            if ticker_reminders:
                reminders.append(f"Yet to purchase {ticker}:\n" + "\n".join(ticker_reminders))

    if reminders:
        reminder_message = "\n\n".join(reminders)
        await send_large_message_chunks(ctx, reminder_message)
    else:
        await ctx.send("All accounts have purchased the necessary stocks.")

async def get_watch_status(ctx, ticker: str):
    """Get the status of a specific stock ticker across all accounts."""
    ticker = ticker.upper()
    account_mapping = load_account_mappings()

    if ticker in watch_list:
        status = f"Status for {ticker}:\n"
        for broker_name, broker_accounts in account_mapping.items():
            total_accounts = len(broker_accounts)
            holding_count = sum(1 for acc_number in broker_accounts if watch_list[ticker][broker_name].get(acc_number, {}).get('steps_completed', 0) >= 2)

            if holding_count > 0:
                status += f"{broker_name}: Position in {holding_count} of {total_accounts} accounts\n"
            else:
                status += f"{broker_name}: No position in {total_accounts} accounts\n"

        await send_chunked_message(ctx, status)
    else:
        await ctx.send(f"{ticker} is not being watched.")

async def list_watched_tickers(ctx):
    """List all currently watched stock tickers with their split dates using an embed."""
    if not watch_list:
        await ctx.send("No tickers are being watched.")
    else:
        embed = discord.Embed(
            title="Watchlist",
            description="All tickers and split dates:",
            color=discord.Color.blue()
        )
        
        for ticker, data in watch_list.items():
            split_date = data.get('split_date', 'N/A')
            embed.add_field(name=f" **|** {ticker}", value=f" **|** Split Date: {split_date} \n", inline=True)
        
        await ctx.send(embed=embed)

async def send_reminder_message_embed(ctx):
    # --- Message content: 
    embed = discord.Embed(
    title="**Watchlist - Upcoming Split Dates: **",
    description=" ",
    color=discord.Color.blue()
    )
    
    # Prepare a list to store tickers and their days left until the split
    sorted_tickers = []

    # Add each ticker and its days left as a field in the embed
    for ticker, data in watch_list.items():
        split_date_str = data['split_date']
        days_left = calculate_days_left(split_date_str)

        # Only include stocks with split dates within 21 days
        if days_left <= 21:
            sorted_tickers.append((days_left, ticker, split_date_str))

    # Sort the list by days_left (first element of the tuple)
    sorted_tickers.sort(key=lambda x: x[0])

    # Add the sorted tickers to the embed
    for days_left, ticker, split_date_str in sorted_tickers:
        embed.add_field(
            name=f"**| {ticker}** - Effective on {split_date_str}",
            value=f"*|>* Must purchase within **{days_left}** day(s).\n",
            inline=False
        )
      
    embed.set_footer(text="Automated message will repeat.")
    # --- End message content
    # Replace with your bot channel

    await ctx.send(embed=embed)

async def send_reminder_message(bot):
    # reminders = []

    # reminders.append(f"**Upcoming split dates from watchlist: **\n")
    
    # for ticker, data in watch_list.items():
    #     split_date_str = data['split_date']
    #     days_left = calculate_days_left(split_date_str)  # No need to await

    #     if days_left <= 21:
    #         reminders.append(f"** | {ticker}** - Effective on {split_date_str}\n *|>* Purchase within {days_left} day(s).")
    
    # reminder_message = "\n".join(reminders)
    # --
    embed = discord.Embed(
    title="**Watchlist - Upcoming Split Dates: **",
    description=" ",
    color=discord.Color.blue()  # You can customize the color
    )
    
    # Prepare a list to store tickers and their days left until the split
    sorted_tickers = []

    # Add each ticker and its days left as a field in the embed
    for ticker, data in watch_list.items():
        split_date_str = data['split_date']
        days_left = calculate_days_left(split_date_str)

        # Only include stocks with split dates within 21 days
        if days_left <= 21:
            sorted_tickers.append((days_left, ticker, split_date_str))

    # Sort the list by days_left (first element of the tuple)
    sorted_tickers.sort(key=lambda x: x[0])

    # Add the sorted tickers to the embed
    for days_left, ticker, split_date_str in sorted_tickers:
        embed.add_field(
            name=f"**| {ticker}** - Effective on {split_date_str}",
            value=f"*|>* Must purchase within **{days_left}** day(s).\n",
            inline=False
        )
    
    embed.set_footer(text="Automated message will repeat.")
    
    # Replace with your bot channel
    channel = bot.get_channel(TARGET_CHANNEL_ID)  # Replace with correct channel ID
    if channel:
        await channel.send(embed=embed)
    else:
        print("Channel not found")

def get_seconds_until_next_reminder(target_hour, target_minute):
    """Calculate the number of seconds until the next occurrence of a specific time (HH:MM)."""
    now = datetime.now()
    target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    if now > target_time:
        # If the target time has already passed today, schedule it for tomorrow
        target_time += timedelta(days=1)
    
    return (target_time - now).total_seconds()

async def periodic_check(bot):
    """Checks watchlist and sends reminders at 9:15 AM and 3:45 PM."""
    while True:
        now = datetime.now()
        
        # Wait until 9:15 AM for the first reminder
        if now.hour < 9 or (now.hour == 9 and now.minute < 15):
            seconds_until_915 = get_seconds_until_next_reminder(9, 15)
            await asyncio.sleep(seconds_until_915)
            await send_reminder_message(bot)
        
        # Wait until 3:45 PM for the next reminder
        seconds_until_345 = get_seconds_until_next_reminder(16, 15)
        # seconds_until_345 = get_seconds_until_next_reminder(15, 45)
        await asyncio.sleep(seconds_until_345)
        await send_reminder_message(bot)
        
        # After 3:45 PM, calculate how long until 9:15 AM the next day
        seconds_until_next_day = get_seconds_until_next_reminder(9, 15)
        await asyncio.sleep(seconds_until_next_day)

def calculate_days_left(split_date_str):
    # Regular function, no await needed
    today = datetime.now().date()
    split_date = datetime.strptime(split_date_str, '%m/%d').replace(year=today.year).date()
    if split_date < today:
        split_date = split_date.replace(year=today.year + 1)
    days_left = (split_date - today).days
    return days_left

async def stop_watching(ctx, ticker: str):
    """Stop watching a stock ticker across all accounts."""
    ticker = ticker.upper()

    if ticker in watch_list:
        del watch_list[ticker]
        save_watch_list()
        await ctx.send(f"Stopped watching {ticker} across all accounts.")
        logging.info(f"Stopped watching {ticker}.")
    else:
        await ctx.send(f"{ticker} is not being watched.")
        logging.info(f"{ticker} was not being watched.")

async def send_chunked_message(ctx, message):
    """Send messages in chunks to avoid exceeding Discord's message length limit."""
    if len(message) > 2000:
        chunks = [message[i:i + 2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            await ctx.send(chunk)
    else:
        await ctx.send(message)

async def watch_ticker_status(ctx, ticker: str):
    """Track the progress of a ticker across all accounts."""
    ticker = ticker.upper()

    if ticker not in watch_list:
        await ctx.send(f"{ticker} is not being watched.")
        return

    total_accounts = sum(len(accounts) for accounts in watch_list[ticker]['brokers'].values())
    buy_count = sum(1 for accounts in watch_list[ticker]['brokers'].values() for acc in accounts.values() if acc['steps_completed'] >= 1)

    progress_message = (
        f"**Progress for {ticker}:**\n"
        f"Accounts bought: {buy_count}/{total_accounts}\n"
        f"Split date: {watch_list[ticker]['split_date']}\n"
    )
    await ctx.send(progress_message)
