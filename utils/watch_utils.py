import asyncio
import csv
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta

import discord
import pandas as pd

from utils.config_utils import (DISCORD_SECONDARY_CHANNEL, SELL_FILE,
                                WATCH_FILE, load_account_mappings, load_config)
from utils.excel_utils import add_stock_to_excel_log
from utils.utility_utils import get_last_stock_price, send_large_message_chunks
from utils.sql_utils import update_historical_holdings

# Load configuration and paths from settings
config = load_config()
account_mapping = load_account_mappings

# WatchList Manager
class WatchListManager:
    """Manages the watch list and sell list for stock tickers."""

    def __init__(self, watch_file, sell_file):
        self.watch_file = watch_file
        self.sell_file = sell_file
        self.watch_list = {}
        self.sell_list = {}
        self.load_watch_list()
        self.load_sell_list()

    def save_watch_list(self):
        """Save the current watch list to a JSON file."""
        try:
            with open(self.watch_file, "w") as file:
                json.dump(self.watch_list, file, default=str)
            logging.info("Watch list saved.")
        except Exception as e:
            logging.error(f"Failed to save watch list: {e}")

    def load_watch_list(self):
        """Load the watch list from a JSON file."""
        if os.path.exists(self.watch_file):
            try:
                with open(self.watch_file, "r") as file:
                    self.watch_list = json.load(file)
                logging.info("Watch list loaded.")
            except (IOError, json.JSONDecodeError) as e:
                logging.error(f"Failed to load watch list: {e}")
        else:
            logging.info("No watch list file found, starting fresh.")

    def save_sell_list(self):
        """Save the sell list to a JSON file."""
        try:
            with open(self.sell_file, "w") as file:
                json.dump(self.sell_list, file, default=str)
            logging.info("Sell list saved.")
        except Exception as e:
            logging.error(f"Failed to save sell list: {e}")

    def load_sell_list(self):
        """Load the sell list from a JSON file."""
        if os.path.exists(self.sell_file):
            try:
                with open(self.sell_file, "r") as file:
                    self.sell_list = json.load(file)
                logging.info("Sell list loaded.")
            except (IOError, json.JSONDecodeError) as e:
                logging.error(f"Failed to load sell list: {e}")
        else:
            logging.info("No sell list file found, starting fresh.")

    
    def add_to_sell_list(ticker: str, broker: str = "all", quantity: float = 1.0, scheduled_time: str = None):
        """Adds a ticker to the sell list if not already present."""
        from datetime import datetime

        ticker = ticker.upper()

        if ticker in sell_list:
            logger.info(f"{ticker} already exists in sell list. Skipping add.")
            return False  # Already scheduled

        if not scheduled_time:
            scheduled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sell_list[ticker] = {
            "broker": broker,
            "quantity": quantity,
            "scheduled_time": scheduled_time,
            "added_on": scheduled_time,
        }
        save_sell_list()
        logger.info(f"Added {ticker} to sell list.")
        return True


    def remove_from_sell_list(self, ticker):
        """Remove a ticker from the sell list."""
        if ticker.upper() in self.sell_list:
            del self.sell_list[ticker.upper()]
            self.save_sell_list()
            return True
        return False

    def get_sell_list(self):
        """Get the current sell list."""
        return self.sell_list

    def add_ticker(self, ticker, split_date, split_ratio="N/A"):
        """Add or update a ticker in the watch list."""
        self.watch_list[ticker.upper()] = {
            "split_date": split_date,
            "split_ratio": split_ratio,
        }
        self.save_watch_list()

    def remove_ticker(self, ticker):
        """Remove a ticker from the watch list."""
        if ticker.upper() in self.watch_list:
            del self.watch_list[ticker.upper()]
            self.save_watch_list()
            return True
        return False

    def ticker_exists(self, ticker):
        """Check if a ticker is already in the watch list."""
        return ticker.upper() in self.watch_list

    def get_watch_list(self):
        """Get the current watch list."""
        return self.watch_list

    async def watch_ticker(self, ctx, ticker: str, split_date: str, split_ratio: str = None):
        """Add a stock ticker with a split date and optional split ratio to the watch list."""
        ticker = ticker.upper()

        if not self.ticker_exists(ticker):
            self.add_ticker(ticker, split_date, split_ratio or "N/A")
            try:
                # Update Excel log for the new ticker
                await add_stock_to_excel_log(ctx, ticker, split_date, split_ratio or "N/A")
                logging.info(f"{ticker} with Split Ratio {split_ratio or 'N/A'} on {split_date} saved to watchlist & Excel log.")
            except Exception as e:
                await ctx.send(f"Error adding {ticker} to the Excel log: {str(e)}")
                logging.error(f"Error adding stock {ticker} to Excel: {str(e)}")
                return

        # Confirmation message
        confirmation_message = (
            f"Watching {ticker} with a reverse split date on {split_date} and split ratio {split_ratio or 'N/A'}."
            if split_ratio
            else f"Watching {ticker} with a reverse split date on {split_date}. To add split ratio, use '..addratio {ticker} ratio'."
        )
        await ctx.send(confirmation_message)

    async def watch_ratio(self, ctx, ticker: str, split_ratio: str):
        ticker = ticker.upper()

        if not self.ticker_exists(ticker):
            await ctx.send(
                f"{ticker} is not currently in the watchlist. Use '..watch TICKER mm/dd [optional ratio]' to add it first."
            )
            return

        if not split_ratio.count("-") == 1:
            await ctx.send("Invalid split ratio format. Use 'X-Y' format (e.g., 1-10).")
            return

        self.add_ticker(
            ticker, self.get_watch_list()[ticker]["split_date"], split_ratio
        )
        await ctx.send(f"Updated the split ratio for {ticker} to {split_ratio}.")
        logging.info(f"Updated split ratio for {ticker} in watchlist to {split_ratio}.")

    async def list_watched_tickers(self, ctx):
        """List all currently watched stock tickers with their split dates using an embed."""
        watch_list = self.get_watch_list()

        if not watch_list:
            await ctx.send("No tickers are being watched.")
        else:
            embed = discord.Embed(
                title="Watchlist",
                description="All tickers and split dates:",
                color=discord.Color.blue(),
            )

            for ticker, data in watch_list.items():
                split_date = data.get("split_date", "N/A")
                last_price = get_last_stock_price(ticker)
                last_price_display = f"{last_price:.2f}" if last_price is not None else "N/A"
                embed.add_field(
                    name=f"{ticker} **|** ${last_price_display}",
                    value=f" **|** Split Date: {split_date} \n",
                    inline=True,
                )

            await ctx.send(embed=embed)

    async def stop_watching(self, ctx, ticker: str):
        """Stop watching a stock ticker across all accounts."""
        ticker = ticker.upper()

        if self.remove_ticker(ticker):
            await ctx.send(f"Stopped watching {ticker} across all accounts.")
            logging.info(f"Stopped watching {ticker}.")
        else:
            await ctx.send(f"{ticker} is not being watched.")
            logging.info(f"{ticker} was not being watched.")

# Initialize WatchList Manager
watch_list_manager = WatchListManager(WATCH_FILE, SELL_FILE)

# Main functions
async def send_reminder_message_embed(ctx):
    """Sends a reminder message with upcoming split dates in an embed."""
    # Create the embed message
    logging.info(f"Sending reminder message at {datetime.now()}")
    update_historical_holdings()
    embed = discord.Embed(
        title="**Watchlist - Upcoming Split Dates: **",
        description=" ",
        color=discord.Color.blue(),
    )

    logging.info(f"Reminder message called for {datetime.now()}")
    update_historical_holdings()
  
    await ctx.send("!rsa holdings all")
    logging.info("Sent holdings refresh command as part of reminder task.")
    
    # Get the watch list from the manager
    watch_list = watch_list_manager.get_watch_list()

    # Prepare a list to store tickers and their days left until the split
    sorted_tickers = []

    # Add each ticker and its days left as a field in the embed
    for ticker, data in watch_list.items():
        split_date_str = data["split_date"]
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
            inline=False,
        )

    embed.set_footer(text="Repeat this message with '..reminder'")

    # Send the embed message to the context
    await ctx.send(embed=embed)


def get_seconds_until_next_reminder(target_hour, target_minute):
    """Calculate the number of seconds until the next occurrence of a specific time (HH:MM)."""
    now = datetime.now()
    target_time = now.replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )

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
        await asyncio.sleep(seconds_until_345)
        await send_reminder_message(bot)

        # After 3:45 PM, calculate how long until 9:15 AM the next day
        seconds_until_next_day = get_seconds_until_next_reminder(9, 15)
        await asyncio.sleep(seconds_until_next_day)


def calculate_days_left(split_date_str):
    # Regular function, no await needed
    today = datetime.now().date()
    split_date = (
        datetime.strptime(split_date_str, "%m/%d").replace(year=today.year).date()
    )
    if split_date < today:
        split_date = split_date.replace(year=today.year + 1)
    days_left = (split_date - today).days
    return days_left


async def send_reminder_message(bot):
    """Sends a reminder message with upcoming split dates in the specified channel."""
    # Create the embed message
    embed = discord.Embed(
        title="**Watchlist - Upcoming Split Dates: **",
        description=" ",
        color=discord.Color.blue(),
    )

    logging.info(f"Automated reminder message for {datetime.now()}")
    update_historical_holdings()

    # Get the watch list from the manager
    watch_list = watch_list_manager.get_watch_list()

    # Prepare a list to store tickers and their days left until the split
    sorted_tickers = []

    # Add each ticker and its days left as a field in the embed
    for ticker, data in watch_list.items():
        split_date_str = data["split_date"]
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
            inline=False,
        )

    embed.set_footer(text="Automated message will repeat.")

    # Send the embed message to the specified channel
    channel = bot.get_channel(DISCORD_SECONDARY_CHANNEL)  # Replace with correct channel ID
    if channel:
        await channel.send(embed=embed)
    else:
        logging.error("Channel not found.")
