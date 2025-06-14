"""Utility helpers for reading and writing CSV trading logs.

This module centralizes all CSV interactions for holdings and order data. It
provides convenience wrappers for checking ticker activity, persisting parsed
holdings or orders, and clearing log files.  The constants ``HOLDINGS_HEADERS``
and ``ORDERS_HEADERS`` define the expected column order for their respective
logs.
"""

import asyncio
import csv
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

import discord
from discord import Embed

from utils.config_utils import HOLDINGS_LOG_CSV, ORDERS_LOG_CSV, load_config
from utils.sql_utils import update_holdings_live

logger = logging.getLogger(__name__)

# Load configuration and mappings
config = load_config()
HOLDINGS_HEADERS = [
    "Key",
    "Broker Name",
    "Broker Number",
    "Account Number",
    "Stock",
    "Quantity",
    "Price",
    "Position Value",
    "Account Total",
    "Timestamp",
]

ORDERS_HEADERS = [
    "Broker Name",
    "Broker Number",
    "Account Number",
    "Order Type",
    "Stock",
    "Quantity",
    "Price",
    "Date",
    "Timestamp",
]


# Utility functions for external tools


def is_ticker_currently_held(ticker: str) -> bool:
    """Returns True if the ticker is currently held based on CSV log."""
    from utils.config_utils import HOLDINGS_LOG_CSV
    import csv
    import os

    if not os.path.exists(HOLDINGS_LOG_CSV):
        return False

    with open(HOLDINGS_LOG_CSV, mode="r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row.get("Stock", "").strip().upper() == ticker.upper():
                try:
                    quantity = float(row.get("Quantity", 0))
                    if quantity > 0:
                        return True
                except ValueError:
                    continue
    return False


def was_ticker_held_recently(ticker: str, days: int = 7) -> bool:
    """Returns True if the ticker appears in CSV with a timestamp within the last X days."""
    from utils.config_utils import HOLDINGS_LOG_CSV
    import csv
    import os

    if not os.path.exists(HOLDINGS_LOG_CSV):
        return False

    cutoff = datetime.now() - timedelta(days=days)

    with open(HOLDINGS_LOG_CSV, mode="r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row.get("Stock", "").strip().upper() == ticker.upper():
                ts = row.get("Timestamp", "")
                try:
                    parsed = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    if parsed >= cutoff:
                        return True
                except Exception:
                    continue
    return False


def ensure_csv_file_exists(file_path, headers):
    if not os.path.exists(file_path):
        with open(file_path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(headers)


def load_csv_log(file_path):
    """Loads existing orders from CSV."""
    if os.path.exists(file_path):
        with open(file_path, mode="r", newline="") as file:
            reader = csv.DictReader(file)
            return list(reader)
    return []


def archive_stale_orders(existing_orders, cutoff_date, archive_file_path):
    """
    Archives stale orders older than the cutoff date into a separate file and returns the updated list of non-stale orders.

    Args:
        existing_orders (list): List of existing orders.
        cutoff_date (datetime): Orders older than this date are considered stale.
        archive_file_path (str): Path to the archive CSV file.

    Returns:
        list: Non-stale orders remaining after archiving.
    """
    # Identify stale orders
    stale_orders = [
        order
        for order in existing_orders
        if datetime.strptime(order["Date"], "%Y-%m-%d") < cutoff_date
    ]

    # Save stale orders to the archive file
    if stale_orders:
        mode = "a" if os.path.exists(archive_file_path) else "w"
        with open(archive_file_path, mode=mode, newline="") as archive_file:
            writer = csv.DictWriter(archive_file, fieldnames=ORDERS_HEADERS)
            if mode == "w":
                writer.writeheader()
            writer.writerows(stale_orders)

    # Filter out stale orders from the original list
    non_stale_orders = [
        order
        for order in existing_orders
        if datetime.strptime(order["Date"], "%Y-%m-%d") >= cutoff_date
    ]

    return non_stale_orders


def identify_latest_orders(orders, new_order):
    """Keeps the latest order for each unique key based on Timestamp."""
    new_order_key = (
        new_order["Broker Name"],
        new_order["Broker Number"],
        new_order["Account Number"],
        new_order["Order Type"].lower(),
        new_order["Stock"].upper(),
        new_order["Date"],
    )

    # Dictionary to store the latest order by key
    latest_orders = {}
    for order in orders:
        order_key = (
            order["Broker Name"],
            order["Broker Number"],
            order["Account Number"],
            order["Order Type"].lower(),
            order["Stock"].upper(),
            order["Date"],
        )

        # Only keep the latest order for each unique key
        if (
            order_key not in latest_orders
            or order["Timestamp"] > latest_orders[order_key]["Timestamp"]
        ):
            latest_orders[order_key] = order

    # Add or replace with the new order if it's the latest
    if new_order_key in latest_orders:
        if new_order["Timestamp"] > latest_orders[new_order_key]["Timestamp"]:
            logger.info(f"Replacing older duplicate with new order: {new_order}")
            latest_orders[new_order_key] = new_order
    else:
        latest_orders[new_order_key] = new_order

    return list(latest_orders.values())


def write_orders_to_csv(orders, file_path):
    """Writes orders to CSV, overwriting the file."""
    with open(file_path, mode="w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=ORDERS_HEADERS)
        writer.writeheader()
        writer.writerows(orders)


def alert_negative_quantity(order_data):
    """
    Checks if the order has a negative Quantity and logs an alert if true.

    Args:
        order_data (dict): The order data being processed.
    """
    try:
        quantity = float(order_data.get("Quantity", 0))
        if quantity < 0:
            logger.warning(f"Negative Quantity detected in order: {order_data}")
            # You can add additional alert mechanisms here (e.g., email, Discord message)
            print(f"ALERT: Negative Quantity detected in order: {order_data}")
    except ValueError:
        logger.error(
            f"Invalid Quantity value in order: {order_data.get('Quantity')}, unable to check for negativity."
        )


def save_order_to_csv(order_data):
    # Saves order, deletes duplicates and stale entries
    try:
        logger.info(f"Processing order data: {order_data}")

        ensure_csv_file_exists(ORDERS_LOG_CSV, ORDERS_HEADERS)
        logger.info(
            "Processing new order in csv_utils, checking for duplicates and stale entries."
        )

        if "Timestamp" not in order_data or not order_data["Timestamp"]:
            order_data["Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Load existing orders
        existing_orders = load_csv_log(ORDERS_LOG_CSV)

        # Check for negative quantity
        alert_negative_quantity(order_data)

        # Archive stale orders
        # cutoff_date = datetime.now() - timedelta(days=30)
        # non_stale_orders = archive_stale_orders(
        #    existing_orders, cutoff_date, ORDERS_LOG_CSV
        # )

        # Identify the latest orders to handle duplicates
        updated_orders = identify_latest_orders(existing_orders, order_data)

        # Write updated orders back to the CSV
        write_orders_to_csv(updated_orders, ORDERS_LOG_CSV)
        logger.info(f"Order saved to csv: {order_data}")

    except Exception as e:
        logger.error(f"Error saving order to CSV: {e}")


# ! --- Holdings Management ---

CURRENT_HOLDINGS = load_csv_log(HOLDINGS_LOG_CSV)


def save_holdings_to_csv(parsed_holdings):
    """Save holdings data to CSV.

    ``parsed_holdings`` may be a list of dictionaries or lists.  Dictionaries
    should use keys such as ``broker``, ``group``, ``account`` and ``ticker`` to
    represent the standard CSV columns (``Broker Name``, ``Broker Number``,
    ``Account Number`` and ``Stock`` respectively).  Lists are treated as
    positional data matching :data:`HOLDINGS_HEADERS` for backward
    compatibility.

    Each entry written to the CSV will contain all :data:`HOLDINGS_HEADERS`
    fields plus a ``Timestamp``.
    """

    # Generate the current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Load existing holdings from the CSV
        existing_holdings = []
        if os.path.exists(HOLDINGS_LOG_CSV):
            with open(HOLDINGS_LOG_CSV, mode="r", newline="") as file:
                reader = csv.DictReader(file)
                existing_holdings = list(reader)

        # Create a set of unique keys to track existing entries
        existing_keys = set(
            (
                holding["Key"],
                holding["Broker Name"],
                holding["Broker Number"],
                holding["Account Number"],
                holding["Stock"],
            )
            for holding in existing_holdings
        )


        # Convert parsed_holdings into a list of dictionaries and filter out duplicates
        new_holdings = []
        for holding in parsed_holdings:
            if isinstance(holding, dict):
                # Map dictionary keys to standard CSV columns
                holding_dict = {
                    "Key": holding.get(
                        "Key",
                        f"{holding.get('broker','')}_{holding.get('group','')}_{holding.get('account','')}_{holding.get('ticker','')}",
                    ),
                    "Broker Name": holding.get("broker") or holding.get("Broker Name", ""),
                    "Broker Number": holding.get("group") or holding.get("Broker Number", ""),
                    "Account Number": holding.get("account") or holding.get("Account Number", ""),
                    "Stock": holding.get("ticker") or holding.get("Stock", ""),
                    "Quantity": holding.get("quantity") or holding.get("Quantity", 0),
                    "Price": holding.get("price") or holding.get("Price", 0),
                    "Position Value": holding.get("value") or holding.get("Position Value", 0),
                    "Account Total": holding.get("account_total") or holding.get("Account Total", 0),
                }
            else:
                # Assume legacy list format
                holding_dict = dict(zip(HOLDINGS_HEADERS, holding))
            holding_key = (
                holding_dict["Key"],
                holding_dict["Broker Name"],
                holding_dict["Broker Number"],
                holding_dict["Account Number"],
                holding_dict["Stock"],
            )

            # Ensure numeric fields are valid
            try:
                holding_dict["Quantity"] = float(holding_dict["Quantity"])
                holding_dict["Price"] = float(holding_dict["Price"])
                holding_dict["Position Value"] = (
                    holding_dict["Quantity"] * holding_dict["Price"]
                )  # Recalculate Position Value
                holding_dict["Account Total"] = float(
                    holding_dict.get("Account Total", 0)
                )  # Optional field
            except (ValueError, KeyError):
                logger.warning(f"Invalid numeric value in holding: {holding_dict}")
                continue  # Skip invalid entries

            # Add timestamp
            holding_dict["Timestamp"] = timestamp

            # Check if this holding is a duplicate
            if holding_key not in existing_keys:
                new_holdings.append(holding_dict)
                existing_keys.add(holding_key)

                # Save to the database
                update_holdings_live(
                    broker=holding_dict["Broker Name"],
                    broker_number=holding_dict["Broker Number"],
                    account_number=holding_dict["Account Number"],
                    ticker=holding_dict["Stock"],
                    quantity=holding_dict["Quantity"],
                    price=holding_dict["Price"],
                )

        # Write the updated holdings to the CSV
        if new_holdings:
            with open(HOLDINGS_LOG_CSV, mode="w", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=HOLDINGS_HEADERS)
                writer.writeheader()
                writer.writerows(
                    existing_holdings + new_holdings
                )  # Append new entries to existing ones

            logger.info(f"Holdings saved, with {len(new_holdings)} new entries added.")
        else:
            logger.info("No new holdings to add.")

    except Exception as e:
        logger.error(f"Error saving holdings: {e}")


def clear_holdings_log(filename):
    """
    Clears all holdings from the CSV file, preserving only the headers.
    Returns True if successful, False otherwise.
    """
    try:
        # Check if the file exists
        if not os.path.exists(filename):
            return False, f'Holdings at: "{filename}" does not exist.'

        # Read the headers from the file
        with open(filename, mode="r") as file:
            reader = csv.reader(file)
            headers = next(reader, None)  # Get the headers from the first row

        if headers:
            # Write only the headers back to the file, clearing the data
            with open(filename, mode="w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(headers)  # Write the headers back
            return (
                True,
                f'Holdings at: "{filename}" has been cleared. Run `!rsa holdings` to repopulate.',
            )
        else:
            return False, f'Holdings at: "{filename}" is empty or improperly formatted.'
    except Exception as e:
        return False, f"Error clearing holdings log: {e}"


# ! --- Sell All Command ---


async def sell_all_position(ctx, broker: str, live_mode: str = "false"):
    """
    Liquidates all holdings for a given brokerage.
    - Checks the holdings log for the brokerage.
    - Sells the smallest quantity found for each stock across all accounts.
    - Runs the sell command for each stock with a 30-second interval.

    Args:
        broker (str): The name of the brokerage to liquidate.
        live_mode (str): Set to "true" for live mode or "false" for dry run mode. Defaults to "false".
    """
    try:
        # Validate live_mode
        if live_mode.lower() not in ["true", "false"]:
            await ctx.send(
                "Invalid live mode. Use 'true' for live mode or 'false' for dry run mode."
            )
            return

        # Load holdings from CSV
        holdings = []
        with open(HOLDINGS_LOG_CSV, mode="r", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["Broker Name"].lower() == broker.lower():
                    holdings.append(row)

        if not holdings:
            await ctx.send(f"No holdings found for brokerage: {broker}.")
            return

        # Group holdings by ticker and calculate minimum quantity
        tickers = {}
        for holding in holdings:
            ticker = holding["Stock"].upper()
            quantity = float(holding["Quantity"])
            if ticker in tickers:
                tickers[ticker] = min(tickers[ticker], quantity)
            else:
                tickers[ticker] = quantity

        # Liquidate each stock
        for ticker, quantity in tickers.items():
            sell_command = f"!rsa sell {quantity} {ticker} {broker} {live_mode}"
            await ctx.send(sell_command)
            logger.info(f"Executed: {sell_command}")

            # Wait 30 seconds before the next stock
            await asyncio.sleep(30)

        await ctx.send(
            f"Liquidation completed for brokerage: {broker} in {'live' if live_mode == 'true' else 'dry'} mode."
        )
        logger.info(f"Liquidation completed for brokerage: {broker}.")

    except Exception as e:
        logger.error(f"Error during liquidation: {e}")
        await ctx.send(f"An error occurred: {str(e)}")


# ! --- Holdings Summaries ---


def get_top_holdings(range=3):
    """
    Aggregates distinct top holdings by broker level.

    Args:
        range (int): Number of top holdings to display per broker.

    Returns:
        dict: Top distinct holdings grouped by broker, latest timestamp.
    """
    logger.info(f"Starting aggregation of top holdings for range: {range}")

    broker_data = defaultdict(list)
    latest_timestamp = None

    try:
        # Filter holdings where Quantity <= 1 and group by broker
        filtered_holdings = []
        for holding in CURRENT_HOLDINGS:
            try:
                quantity = float(holding.get("Quantity", 0))
                if quantity <= 1:
                    filtered_holdings.append(holding)
                    # Update the latest timestamp
                    timestamp = holding.get("Timestamp")
                    if timestamp:
                        parsed_timestamp = datetime.strptime(
                            timestamp, "%Y-%m-%d %H:%M:%S"
                        )
                        if not latest_timestamp or parsed_timestamp > latest_timestamp:
                            latest_timestamp = parsed_timestamp
            except ValueError:
                logger.warning(
                    f"Skipping invalid Quantity value: {holding.get('Quantity')} in holding: {holding}"
                )
                continue

        logger.debug(f"Filtered {len(filtered_holdings)} holdings where Quantity <= 1.")

        # Group by broker while ensuring distinct tickers
        for holding in filtered_holdings:
            broker_name = holding.get("Broker Name")
            stock_ticker = holding.get("Stock")  # Stock ticker to check uniqueness
            if stock_ticker == "Cash and Sweep Funds":
                continue
            if broker_name and stock_ticker:
                # Ensure no duplicates of the same stock ticker for the broker
                existing_tickers = {h.get("Stock") for h in broker_data[broker_name]}
                if stock_ticker not in existing_tickers:
                    broker_data[broker_name].append(holding)
                    logger.debug(
                        f"Added distinct holding for broker '{broker_name}': {holding}"
                    )
                    print(
                        f"Added distinct holding for broker '{broker_name}': {holding}"
                    )

        # Sort and take the top X (range) for each broker
        top_range = {}
        for broker, holdings_list in broker_data.items():
            sorted_holdings = sorted(
                holdings_list,
                key=lambda x: float(x.get("Position Value", 0)),
                reverse=True,
            )[:range]
            top_range[broker] = sorted_holdings
            logger.info(
                f"Top {range} distinct holdings for broker '{broker}': {sorted_holdings}"
            )

        logger.info("Completed aggregation of top holdings.")
        return top_range, latest_timestamp

    except Exception as e:
        logger.error(f"Error in get_top_holdings: {e}", exc_info=True)
        return {}


async def send_top_holdings_embed(ctx, range):
    """
    Sends the top holdings by broker as an embed message.

    Args:
        ctx: Discord context object.
        range (int): Number of holdings displayed per broker.
    """
    try:
        logger.info(f"Preparing to send top holdings embed for range: {range}")

        # Get top holdings and latest timestamp
        top_holdings, latest_timestamp = get_top_holdings(range)

        if not top_holdings:
            logger.warning("No holdings found to display.")
            await ctx.send("No holdings found.")
            return

        # Format the timestamp for the footer
        formatted_timestamp = (
            latest_timestamp.strftime("%B %d, %Y at %I:%M %p")
            if latest_timestamp
            else "Unknown"
        )

        # Create embed
        embed = discord.Embed(
            title=f"Top {range} Holdings by Broker < R/S Only >",
            color=discord.Color.blue(),
        )

        for broker, holdings in top_holdings.items():
            if holdings:
                holding_details = "\n".join(
                    f"**{holding['Stock']}**: ${float(holding['Position Value']):,.2f})"
                    for holding in holdings
                )
                embed.add_field(name=broker, value=holding_details, inline=True)
                logger.debug(f"Added broker '{broker}' to embed.")
            else:
                embed.add_field(name=broker, value="No holdings found.", inline=True)
                logger.debug(f"No holdings found for broker '{broker}'.")

        # Add footer with the latest timestamp
        embed.set_footer(text=f"< - - <-> - - > \nData as of {formatted_timestamp}")

        # Send embed
        await ctx.send(embed=embed)
        logger.info("Embed message sent successfully.")

    except Exception as e:
        logger.error(f"Error in send_top_holdings_embed: {e}", exc_info=True)
        await ctx.send(f"An error occurred while preparing the embed: {e}")
