import asyncio
import csv
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta

import discord
import pandas as pd

from utils.config_utils import (get_account_nickname, load_account_mappings,
                                load_config, send_large_message_chunks,
                                should_skip)
from utils.excel_utils import add_stock_to_excel_log

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
            'reminder_sent': False
        }
        add_stock_to_excel_log(ticker, EXCEL_XLSX_FILE)
        logging.info("Added stock to watchlist and passed to excel utils.")
    await ctx.send(f"Watching {ticker} with a reverse split date on {split_date}.")
    save_watch_list()

def update_watchlist(broker_name, account_nickname, stock, quantity, order_type=None):
    """This function has been deprecated and no longer updates the watchlist."""
    print(f"update_watchlist called for stock: {stock}, but this function is deprecated.")
    # You could even raise a warning to make sure it’s not used inadvertently in the future.
    # import warnings
    # warnings.warn("update_watchlist is deprecated and no longer updates the watchlist", DeprecationWarning)


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

        await send_large_message_chunks(ctx, status)
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
