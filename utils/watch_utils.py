"""Utility helpers for managing watch and sell lists.

This module relies on :func:`utils.config_utils.load_account_mappings` to load
broker account information used across various watch list operations.
"""

import asyncio
import csv
import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta

import discord
import pandas as pd

from utils.config_utils import (
    DISCORD_SECONDARY_CHANNEL,
    DISCORD_PRIMARY_CHANNEL,
    SELL_FILE,
    WATCH_FILE,
    load_account_mappings,
    AUTO_REFRESH_ON_REMINDER,
)
from utils.excel_utils import add_stock_to_excel_log
from utils.utility_utils import send_large_message_chunks
from utils.price_fetcher import get_last_prices
from utils.sql_utils import update_historical_holdings
from rsassistant.bot.channel_resolver import resolve_reply_channel
from utils.market_calendar import MARKET_TZ, is_market_day

account_mapping = load_account_mappings()


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

    def add_to_sell_list(self, ticker, broker, quantity, scheduled_time):
        """
        Add a ticker with details to the sell list.
        """
        self.sell_list[ticker.upper()] = {
            "broker": broker,
            "quantity": quantity,
            "scheduled_time": scheduled_time,
            "added_on": datetime.now().strftime("%Y-%m-%d"),
        }
        self.save_sell_list()

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

    def move_expired_to_sell(self):
        """Move tickers with past split dates to the sell list."""
        today = datetime.now().date()
        to_remove = []
        for ticker, data in list(self.watch_list.items()):
            split_str = data.get("split_date")
            if not split_str:
                continue
            split_dt = None
            # Try common date formats (month/day with optional year)
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%d"):
                try:
                    split_dt = datetime.strptime(split_str, fmt)
                    if fmt == "%m/%d":
                        split_dt = split_dt.replace(year=today.year)
                    break
                except ValueError:
                    continue
            if not split_dt:
                logging.error(f"Unable to parse split date '{split_str}' for {ticker}.")
                continue

            if split_dt.date() < today:
                if ticker.upper() not in self.sell_list:
                    self.add_to_sell_list(
                        ticker=ticker,
                        broker="all",
                        quantity=0,
                        scheduled_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    )
                to_remove.append(ticker.upper())

        for ticker in to_remove:
            if ticker in self.watch_list:
                del self.watch_list[ticker]
        if to_remove:
            self.save_watch_list()

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

    async def watch_ticker(self, ctx, ticker, split_date, split_ratio=None):
        """Add a stock ticker with a split date and optional split ratio to the watch list."""
        ticker = ticker.upper()

        if not self.ticker_exists(ticker):
            self.add_ticker(ticker, split_date, split_ratio or "N/A")
            try:
                # Update Excel log for the new ticker
                await add_stock_to_excel_log(
                    ctx, ticker, split_date, split_ratio or "N/A"
                )
                logging.info(
                    f"{ticker} with Split Ratio {split_ratio or 'N/A'} on {split_date} saved to watchlist & Excel log."
                )
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

    async def list_watched_tickers(
        self, ctx, include_prices: bool = False
    ) -> None:
        """List all watched tickers with split details.

        Args:
            ctx: Discord command context used to send the response.
            include_prices: When ``True`` append the latest known price to the
                field title for each ticker. Defaults to ``False``.
        """
        watch_list = self.get_watch_list()

        if not watch_list:
            await ctx.send("No tickers are being watched.")
            return

        embed = discord.Embed(
            title="Watchlist",
            description="Tracked reverse split candidates:",
            color=discord.Color.blue(),
        )

        prices = {}
        if include_prices:
            prices = get_last_prices(watch_list.keys())

        for ticker, data in sorted(watch_list.items()):
            split_date = data.get("split_date", "N/A")
            split_ratio = data.get("split_ratio", "N/A")
            field_name = ticker
            if include_prices:
                last_price = prices.get(ticker)
                price_display = (
                    f"${last_price:.2f}" if last_price is not None else "N/A"
                )
                field_name = f"{ticker} — {price_display}"

            value_lines = [f"Split Date: {split_date}", f"Split Ratio: {split_ratio}"]
            embed.add_field(name=field_name, value="\n".join(value_lines), inline=False)

        await ctx.send(embed=embed)

    async def send_watchlist_prices(self, ctx) -> None:
        """Send a plain-text list of watchlist tickers with the latest prices."""
        watch_list = self.get_watch_list()

        if not watch_list:
            await ctx.send("No tickers are being watched.")
            return

        prices = get_last_prices(watch_list.keys())
        lines = []
        for ticker in sorted(watch_list.keys()):
            last_price = prices.get(ticker)
            price_display = f"${last_price:.2f}" if last_price is not None else "N/A"
            lines.append(f"{ticker}: {price_display}")

        await send_large_message_chunks(ctx, "\n".join(lines))

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
    watch_list_manager.move_expired_to_sell()
    embed = discord.Embed(
        title="**Watchlist - Upcoming Split Dates: **",
        description=" ",
        color=discord.Color.blue(),
    )

    logging.info(f"Reminder message called for {datetime.now()}")
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
    now = datetime.now(MARKET_TZ)
    if not is_market_day(now.date()):
        logging.info("Skipping reminder message on non-market day: %s", now.date())
        return

    # Create the embed message
    embed = discord.Embed(
        title="**Watchlist - Upcoming Split Dates: **",
        description=" ",
        color=discord.Color.blue(),
    )

    logging.info(f"Automated reminder message for {datetime.now()}")
    update_historical_holdings()
    watch_list_manager.move_expired_to_sell()

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

    channel = resolve_reply_channel(bot, DISCORD_SECONDARY_CHANNEL)
    if not channel:
        channel = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
    if not channel:
        channel = resolve_reply_channel(bot)

    if channel:
        await channel.send(embed=embed)
    else:
        logging.error("No configured channel available for reminder message.")

    # Optionally trigger a holdings refresh in the primary channel
    try:
        if AUTO_REFRESH_ON_REMINDER:
            primary = resolve_reply_channel(bot, DISCORD_PRIMARY_CHANNEL)
            if not primary:
                primary = resolve_reply_channel(bot)
            if primary:
                await primary.send("!rsa holdings all")
                logging.info("Triggered holdings refresh due to reminder (AUTO_REFRESH_ON_REMINDER=true)")
            else:
                logging.error(
                    "No configured channel found for auto holdings refresh command."
                )
    except Exception as e:
        logging.error(f"Error triggering auto holdings refresh: {e}")


def parse_bulk_watchlist_message(content: str):
    """Parse bulk watchlist entries in the ``ticker ratio (purchase by mm/dd)`` format.

    Each non-empty line is expected to follow the structure
    ``TICKER 1-10 (purchase by 10/24)``, where the ratio component is optional
    and the date portion may be supplied as ``mm/dd``, ``mm/dd/yy`` or
    ``mm/dd/yyyy``. The function returns a list of tuples structured as
    ``(ticker, date, ratio)`` suitable for :meth:`WatchListManager.watch_ticker`.
    """

    entries = []
    pattern = re.compile(
        r"^(?P<ticker>[A-Za-z]+)\s+(?:(?P<ratio>\d+-\d+)\s+)?\(purchase by\s+(?P<date>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\)",
        re.IGNORECASE,
    )
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        match = pattern.match(line)
        if match:
            data = match.groupdict()
            entries.append((data["ticker"].upper(), data["date"], data.get("ratio")))
    return entries


def _is_valid_split_date(date_token: str) -> bool:
    """Return ``True`` when ``date_token`` uses a supported month/day format."""

    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m/%d"):
        try:
            datetime.strptime(date_token, fmt)
            return True
        except ValueError:
            continue
    return False


def _parse_watch_flags(text: str):
    """Parse flag-based watch arguments from a text string."""
    tokens = text.split()
    if not tokens or not tokens[0].startswith("-"):
        return None, None

    ticker = None
    split_date = None
    split_ratio = None

    i = 0
    while i < len(tokens):
        token = tokens[i]
        value = None
        if "=" in token:
            flag, value = token.split("=", 1)
        else:
            flag = token

        if flag in ("-t", "--ticker"):
            if value is None:
                i += 1
                if i >= len(tokens):
                    return None, "Missing value for --ticker."
                value = tokens[i]
            ticker = value
        elif flag in ("-d", "--date"):
            if value is None:
                i += 1
                if i >= len(tokens):
                    return None, "Missing value for --date."
                value = tokens[i]
            split_date = value
        elif flag in ("-r", "--ratio"):
            if value is None:
                i += 1
                if i >= len(tokens):
                    return None, "Missing value for --ratio."
                value = tokens[i]
            split_ratio = value
        else:
            return None, f"Unknown flag: {flag}"
        i += 1

    return {
        "ticker": ticker,
        "split_date": split_date,
        "split_ratio": split_ratio,
    }, None


async def watch(ctx, *, text: str):
    """Discord command handler for ``..watch``.

    Supports either the traditional format ``..watch TICKER mm/dd [ratio]`` or a
    multi-line block of entries like ``TICKER 1-10 (purchase by 6/5)``. In both
    cases the parsed ticker(s) are forwarded to
    :meth:`WatchListManager.watch_ticker` for persistence.
    """
    entries = parse_bulk_watchlist_message(text)
    if entries:
        count = await add_entries_from_message(text, ctx)
        await ctx.send(f"Added {count} tickers to watchlist.")
        return

    parsed_flags, flag_error = _parse_watch_flags(text)
    if flag_error:
        await ctx.send(f"{flag_error} Usage: `..watch -t TICKER -d mm/dd [-r X-Y]`.")
        return
    if parsed_flags:
        ticker = parsed_flags["ticker"]
        split_date = parsed_flags["split_date"]
        split_ratio = parsed_flags["split_ratio"]

        if not ticker or not split_date:
            await ctx.send("Usage: `..watch -t TICKER -d mm/dd [-r X-Y]`.")
            return

        if not _is_valid_split_date(split_date):
            await ctx.send(
                "Invalid date format. Please use mm/dd, mm/dd/yy, or mm/dd/yyyy."
            )
            return

        if split_ratio and split_ratio.count("-") != 1:
            await ctx.send("Invalid split ratio format. Use 'X-Y' (e.g., 1-10).")
            return

        await watch_list_manager.watch_ticker(ctx, ticker, split_date, split_ratio)
        return

    parts = text.split()
    if len(parts) < 2:
        await ctx.send(
            "Usage: '..watch TICKER mm/dd [ratio]' or '..watch -t TICKER -d mm/dd [-r X-Y]' or paste multiple lines."
        )
        return

    ticker = parts[0]
    split_date = parts[1]
    split_ratio = parts[2] if len(parts) > 2 else None

    if not _is_valid_split_date(split_date):
        await ctx.send(
            "Invalid date format. Please use mm/dd, mm/dd/yy, or mm/dd/yyyy."
        )
        return

    if split_ratio and split_ratio.count("-") != 1:
        await ctx.send("Invalid split ratio format. Use 'X-Y' (e.g., 1-10).")
        return

    await watch_list_manager.watch_ticker(ctx, ticker, split_date, split_ratio)


async def add_entries_from_message(content: str, ctx=None) -> int:
    """Add multiple watchlist entries parsed from a message."""
    entries = parse_bulk_watchlist_message(content)
    for ticker, date, ratio in entries:
        if ctx is not None:
            await watch_list_manager.watch_ticker(ctx, ticker, date, ratio)
        else:
            watch_list_manager.add_ticker(ticker, date, ratio)
    return len(entries)
