"""Utility helpers for account mapping and Discord interactions."""

import asyncio
import csv
import json
import logging

logger = logging.getLogger(__name__)
import os
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import discord
import yaml
import yfinance as yf
from utils.yfinance_cache import get_price

from utils.config_utils import (
    ACCOUNT_MAPPING,
    HOLDINGS_LOG_CSV,
    ORDERS_LOG_CSV,
    get_account_nickname,
    load_account_mappings,
    load_config,
)

# Load configuration and holdings data
config = load_config()


def check_holdings_timestamp(filename):
    """Reads the latest timestamp from the specified CSV file."""
    try:
        with open(filename, mode="r") as file:
            reader = csv.DictReader(file)
            rows = list(reader)  # Load all rows to get the last timestamp
            if rows:
                return rows[-1].get("Timestamp", "Timestamp not available")
            else:
                return "No entries in CSV"
    except FileNotFoundError:
        return "CSV file not found"


## -- Print raw order data to term for debugging
def debug_insert_order_history(order_data):
    """Debug function to log and return the order data instead of saving it."""
    try:
        # Return the raw data being passed for inspection
        return order_data
    except Exception as e:
        logging.error(f"Error processing order data for debug: {e}")
        return None


def debug_order_data(order_data):
    debug_data = debug_insert_order_history(order_data)
    logger.debug(f"Order data being passed to SQL: {debug_data}")


HOLDINGS_TIMESTAMP = check_holdings_timestamp(HOLDINGS_LOG_CSV)


async def track_ticker_summary(
    ctx,
    ticker,
    show_details=False,
    specific_broker=None,
    holding_logs_file=HOLDINGS_LOG_CSV,
    account_mapping_file=ACCOUNT_MAPPING,
):
    """
    Track accounts that hold the specified ticker, aggregating at the broker level.
    Shows details at the account level if a specific broker is provided.
    """
    holdings = {}
    ticker = ticker.upper().strip()  # Standardize ticker format

    # Load account mappings
    mapped_accounts = load_account_mappings()

    try:
        # Read holdings log
        with open(holding_logs_file, mode="r") as file:
            csv_reader = csv.DictReader(file)

            for row in csv_reader:
                account_key = row["Key"]  # "Broker Name + Nickname"
                stock = row["Stock"].upper().strip()  # Standardize stock symbol

                # Parse quantity, price, and account total
                try:
                    quantity = float(row["Quantity"])
                    price = float(row["Price"])
                    account_total = float(row["Account Total"])
                except ValueError:
                    continue  # Skip rows where Quantity, Price, or Account Total are invalid

                broker_name = row["Broker Name"]

                # Initialize broker in holdings if not present
                if broker_name not in holdings:
                    holdings[broker_name] = {}

                # Store detailed data in a dictionary
                if stock == ticker and quantity > 0:
                    holdings[broker_name][account_key] = {
                        "status": "✅",
                        "Quantity": quantity,
                        "Price": price,
                        "Account Total": account_total,
                    }
                else:
                    # Only set to "❌" if not already marked as holding, to avoid overwriting
                    if account_key not in holdings[broker_name]:
                        holdings[broker_name][account_key] = {
                            "status": "❌",
                            "Quantity": "N/A",
                            "Price": "N/A",
                            "Account Total": "N/A",
                        }

        # Decide which view to show based on the specific_broker argument
        if specific_broker:
            await get_detailed_broker_view(
                ctx, ticker, specific_broker, holdings, mapped_accounts
            )
        else:
            await get_aggregated_broker_summary(ctx, ticker, holdings, mapped_accounts)

    except FileNotFoundError:
        await ctx.send(
            f"Error: The file {holding_logs_file} or {account_mapping_file} was not found."
        )
    except KeyError as e:
        await ctx.send(f"Error: Missing expected column in CSV: {e}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


async def get_aggregated_broker_summary(ctx, ticker, holdings, account_mapping):
    """
    Generates an aggregated summary of positions across all brokers for a given ticker.
    """
    embed = discord.Embed(
        title=f"**{ticker} Holdings Summary**",
        description=f"All brokers summary, checking position for {ticker}.",
        color=discord.Color.blue(),
    )

    for broker_name, group_data in account_mapping.items():
        if isinstance(group_data, dict):
            # Count the total accounts and held accounts for each broker
            total_accounts = 0
            held_accounts = 0

            for group_number, accounts in group_data.items():
                if isinstance(accounts, dict):
                    total_accounts += len(
                        accounts
                    )  # Add all accounts under the broker to total count
                    for account_number, account_nickname in accounts.items():
                        account_key = f"{broker_name} {account_nickname}"
                        # Check if the account is marked as holding the ticker
                        if (
                            holdings.get(broker_name, {})
                            .get(account_key, {})
                            .get("status")
                            == "✅"
                        ):
                            held_accounts += 1

            # Determine status icon based on counts
            if held_accounts == total_accounts:
                status_icon = "✅"  # All accounts hold the position
            elif held_accounts == 0:
                status_icon = "❌"  # No accounts hold the position
            else:
                status_icon = "🟡"  # Some accounts hold the position

            # Add broker summary field to the embed
            embed.add_field(
                name=f"{broker_name} {status_icon}",
                value=f"Position in {held_accounts} of {total_accounts} accounts",
                inline=True,
            )

    # Add footer with timestamp
    embed.set_footer(
        text=f"Try: '..brokerwith {ticker} <broker>' for details. • {HOLDINGS_TIMESTAMP}"
    )
    await ctx.send(embed=embed)


async def get_detailed_broker_view(
    ctx, ticker, specific_broker, holdings, account_mapping
):
    """
    Organizes the detailed view for a specific broker, calling separate functions to display:
    - Accounts holding the position.
    - Accounts not holding the position.
    """
    broker_name = specific_broker.capitalize()
    logger.debug(f"looking up {broker_name} in mapping")

    if specific_broker.upper() == "BBAE":
        broker_name = "BBAE"  # Ensures 'BBAE' is always in all caps for the lookup

    logger.debug(f"looking up{broker_name}")

    accounts_with_position = []
    accounts_without_position = []

    if broker_name in account_mapping:
        broker_data = account_mapping[broker_name]

        # Traverse groups and accounts within the specified broker
        for group_number, accounts in broker_data.items():
            if isinstance(accounts, dict):
                for account_number, account_nickname in accounts.items():
                    account_key = f"{broker_name} {account_nickname}"
                    account_entry = holdings.get(broker_name, {}).get(account_key)

                    if account_entry and account_entry.get("status") == "✅":
                        # Account holds the ticker; gather details
                        quantity = account_entry.get("Quantity", "N/A")
                        try:
                            price = f"${float(account_entry.get('Price', 0)):,.2f}"
                            account_total = (
                                f"${float(account_entry.get('Account Total', 0)):,.2f}"
                            )
                        except (ValueError, TypeError):
                            price, account_total = "$0.00", "$0.00"
                        accounts_with_position.append(
                            (
                                account_nickname,
                                account_number[-4:],
                                quantity,
                                price,
                                account_total,
                            )
                        )
                    else:
                        # Account does not hold the ticker
                        accounts_without_position.append(
                            (account_nickname, account_number[-4:])
                        )

        # Send embeds for accounts with and without position
        await send_accounts_with_position_embed(
            ctx, broker_name, ticker, accounts_with_position
        )
        await send_accounts_without_position_embed(
            ctx, broker_name, ticker, accounts_without_position
        )
    else:
        await ctx.send(f"No broker found for {broker_name}.")


async def send_accounts_with_position_embed(
    ctx, broker_name, ticker, accounts_with_position
):
    """
    Creates and sends an embed for accounts that hold the ticker position.
    """
    if accounts_with_position:
        # Embed for accounts with the position
        embed_with_position = discord.Embed(
            title=f"{broker_name} Account Holdings {ticker}",
            color=discord.Color.green(),
        )
        # Add account details for each holding position
        for (
            nickname,
            last_four,
            quantity,
            price,
            account_total,
        ) in accounts_with_position:
            embed_with_position.add_field(
                name=f"{nickname} ✅",
                value=(
                    f"Account: {last_four}\n"
                    f"Quantity: {quantity}\n"
                    f"Price: {price}\n"
                    f"Account Total: {account_total}"
                ),
                inline=True,
            )
        # Add footer with the timestamp from HOLDINGS_TIMESTAMP
        embed_with_position.set_footer(
            text=f"Detailed holdings for {ticker} • {HOLDINGS_TIMESTAMP}"
        )
        await ctx.send(embed=embed_with_position)
    else:
        # Embed indicating no holdings
        embed_with_position = discord.Embed(
            title=f"{broker_name} Account Holdings {ticker}",
            description="No accounts hold this position",
            color=discord.Color.red(),
        )
        embed_with_position.set_footer(text=HOLDINGS_TIMESTAMP)
        await ctx.send(embed=embed_with_position)


async def send_accounts_without_position_embed(
    ctx, broker_name, ticker, accounts_without_position
):
    """
    Creates and sends an embed for accounts that do not hold the ticker position.
    """
    if accounts_without_position:
        # Create an embed for accounts without the position
        embed_without_position = discord.Embed(
            title=f"{broker_name} Accounts Not Holding {ticker}",
            color=discord.Color.blue(),
        )
        # Add each account that does not hold the position
        for nickname, last_four in accounts_without_position:
            embed_without_position.add_field(
                name=f"{nickname} ❌",
                value=f"Account: {last_four}\nNo position in {ticker}",
                inline=True,
            )
        # Add footer with the timestamp from HOLDINGS_TIMESTAMP
        embed_without_position.set_footer(
            text=f"Accounts without holdings for {ticker} • {HOLDINGS_TIMESTAMP}"
        )
        await ctx.send(embed=embed_without_position)
    else:
        # Optional embed if all accounts hold the position (for cases where there are no non-holding accounts)
        embed_without_position = discord.Embed(
            title=f"{broker_name} Accounts Not Holding {ticker}",
            description="All accounts hold this position",
            color=discord.Color.green(),
        )
        embed_without_position.set_footer(text=HOLDINGS_TIMESTAMP)
        await ctx.send(embed=embed_without_position)


async def all_brokers(ctx):
    account_mapping = load_account_mappings()
    try:
        active_brokers = list(account_mapping.keys())
        chunk_size = 9
        for i in range(0, len(active_brokers), chunk_size):
            embed = discord.Embed(
                title="**Active Brokers**", color=discord.Color.blue()
            )
            chunk_brokers = active_brokers[i : i + chunk_size]
            for broker in chunk_brokers:
                broker_data = account_mapping.get(broker)
                if not isinstance(broker_data, dict):
                    await ctx.send(f"Error: Broker '{broker}' has invalid data.")
                    continue

                total_holdings, account_count = 0, 0
                for group_number, accounts in broker_data.items():
                    try:
                        group_account_count, group_total = sum_account_totals(
                            broker, group_number, accounts
                        )
                        account_count += group_account_count
                        total_holdings += group_total
                    except ValueError as ve:
                        logging.error(
                            f"Value error for broker {broker}, group {group_number}: {ve}"
                        )
                        continue

                embed.add_field(
                    name=broker,
                    value=f"{account_count} accounts\nTotal: ${total_holdings:,.2f}",
                    inline=True,
                )

            await ctx.send(embed=embed)
            await asyncio.sleep(1)

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")
        logging.error(f"Exception in all_brokers: {e}")


# Retrieve Last Stock Price
def get_last_stock_price(stock):
    """Fetches the last price of a given stock using Yahoo Finance with caching."""
    price = get_price(stock)
    if price is None:
        logging.warning(f"No stock data found for {stock}.")
    return price


# -- Get Totals for Specific Broker
def get_account_totals(broker, group_number=None, account_number=None):
    """
    Retrieve the account totals for specified broker, group, and account from holdings_log.csv.

    Parameters:
        broker (str): The broker to get account totals for.
        group_number (str, optional): The group number to filter accounts.
        account_number (str, optional): The account number to filter accounts.

    Returns:
        dict: Account totals with account numbers as keys and their totals as values.
    """
    account_totals = {}

    with open(HOLDINGS_LOG_CSV, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row["Broker Name"].lower() == broker.lower():
                if group_number and row["Broker Number"] != str(group_number):
                    continue
                if account_number and row["Account Number"] != str(account_number):
                    continue
                account_totals[row["Account Number"]] = float(row["Account Total"])

    return account_totals


# Sum Account Totals by Broker and Group
def sum_account_totals(broker, group_number, accounts):
    """
    Sum the 'Account Total' for all accounts under a specific broker and group from holdings_log.csv.

    Parameters:
        broker (str): The broker for which to sum account totals.
        group_number (str): The group number under the broker.
        accounts (dict): Dictionary of account numbers and their nicknames.

    Returns:
        tuple: The total number of accounts and the sum of all account totals for the broker and group.
    """
    total_sum = 0.0
    account_count = 0
    account_totals = get_account_totals(broker, group_number)

    for account_number in accounts.keys():
        if account_number in account_totals:
            try:
                total_sum += float(account_totals[account_number])
                account_count += 1
            except ValueError:
                logging.warning(
                    f"Account total for '{account_number}' is not a valid number."
                )
                continue

    return account_count, total_sum


# Calculate Totals for All Brokers and Groups
def calculate_broker_totals(account_mapping):
    """
    Calculate total number of accounts and total holdings for each broker and group.

    Parameters:
        account_mapping (dict): The account mappings loaded from account_mapping.json.

    Returns:
        dict: Broker and group totals.
    """
    broker_totals = {}
    for broker, groups in account_mapping.items():
        broker_totals[broker] = {}
        for group_number, accounts in groups.items():
            account_count, total_holdings = sum_account_totals(
                broker, group_number, accounts
            )
            broker_totals[broker][group_number] = {
                "account_count": account_count,
                "total_holdings": total_holdings,
            }

    return broker_totals


# Get All Accounts for a Broker
def all_broker_accounts(broker):
    """
    Retrieve all accounts (nicknames and numbers) for a given broker.

    Parameters:
        broker (str): The broker to retrieve accounts for.

    Returns:
        list or str: List of accounts if found, or an error message if the broker is not found.
    """
    mappings = load_account_mappings()
    if broker not in mappings:
        return (
            f"Broker '{broker}' not found. Available brokers: {list(mappings.keys())}"
        )
    return mappings[broker].get("accounts", [])


# Retrieve Account Nicknames for a Broker
async def all_account_nicknames(ctx, broker):
    """
    Retrieve all account nicknames for a given broker, including group numbers.

    Parameters:
        ctx (discord.Context): The Discord context to send messages to.
        broker (str): The broker to retrieve account nicknames for.
    """
    mappings = load_account_mappings()
    broker_lower = broker.lower()
    normalized_mappings = {key.lower(): key for key in mappings}

    if broker_lower not in normalized_mappings:
        available_brokers = ", ".join(mappings.keys())
        await ctx.send(
            f"Broker {broker} not found. Available brokers: {available_brokers}"
        )
        return

    original_broker = normalized_mappings[broker_lower]
    broker_groups = mappings[original_broker]
    total_sum = sum(
        sum_account_totals(original_broker, group, accounts)[1]
        for group, accounts in broker_groups.items()
    )

    embed = discord.Embed(
        title=f"**{original_broker}**",
        description=f"All active accounts. Total Holdings: ${total_sum:,.2f}",
        color=discord.Color.blue(),
    )

    for group_number, accounts in broker_groups.items():
        account_totals = get_account_totals(original_broker, group_number)
        for account_number, nickname in accounts.items():
            total = account_totals.get(account_number, 0.0)
            embed.add_field(
                name=f"{group_number} - {nickname}",
                value=f"Total: ${total:,.2f}",
                inline=True,
            )

    await ctx.send(embed=embed)


# Get All Account Numbers for a Broker
def all_account_numbers(broker):
    """
    Retrieve all account numbers for a given broker.

    Parameters:
        broker (str): The broker to retrieve account numbers for.

    Returns:
        list or str: List of account numbers or an error message if not found.
    """
    accounts = all_broker_accounts(broker)
    if isinstance(accounts, str):
        return accounts
    return [account["account_number"] for account in accounts]


def all_brokers_summary_by_owner(specific_broker=None):
    """
    Summarizes account totals for each broker, grouped by account owner.

    Parameters:
        specific_broker (str, optional): If provided, only summarize for this broker.

    Returns:
        dict: Dictionary with each broker’s total holdings grouped by owner.
    """
    group_titles = config.get("account_owners", {})
    brokers_summary = {}

    # Debug: log the structure of account_mapping
    logger.debug("\nAccount Mapping Structure:")
    for broker, broker_data in ACCOUNT_MAPPING.items():
        logger.debug(f"{broker}: {broker_data}")

    processed_accounts = set()  # Track processed accounts to avoid duplicates

    with open(HOLDINGS_LOG_CSV, newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            broker_name = row["Broker Name"]
            if specific_broker and broker_name.lower() != specific_broker.lower():
                continue  # Skip if we're filtering by a specific broker

            account_number = row["Account Number"]
            if (broker_name, account_number) in processed_accounts:
                # print(
                #     f"Skipping duplicate entry for {broker_name}, Account Number: {account_number}"
                # )
                continue  # Skip if this account has already been processed

            total_str = row["Account Total"].strip()

            # Skip empty or invalid account total values
            try:
                total = float(total_str) if total_str else 0.0
            except ValueError:
                logger.debug(f"Skipping invalid total in row: {row}")
                continue

            # Mark this account as processed
            processed_accounts.add((broker_name, account_number))

            # Debug: Print account lookup details
            # print(
            #    f"\nProcessing Broker: {broker_name}, Account Number: {account_number}"
            # )

            nickname = ""
            if broker_name in ACCOUNT_MAPPING:
                for broker_number, accounts in ACCOUNT_MAPPING[broker_name].items():
                    if account_number in accounts:
                        nickname = accounts[account_number]
                        break

            logger.debug(f"Fetched Nickname: '{nickname}'")

            if not nickname:
                logger.debug(
                    f"No nickname found for Broker: {broker_name}, Account Number: {account_number}"
                )

            owner = "Uncategorized"  # Default to Uncategorized
            matched = False

            # Match the owner based on account_owners' indicators in the nickname
            for indicator, owner_name in group_titles.items():
                logger.debug(f"Checking if '{indicator}' in nickname '{nickname}'...")
                if indicator in nickname:
                    owner = owner_name
                    matched = True
                    logger.debug(
                        f"Match found! Indicator: '{indicator}' -> Owner: {owner}"
                    )
                    break
                # else:
                # print(
                #    f"No match for indicator '{indicator}' in nickname '{nickname}'."
                # )

            # Initialize broker in summary if it doesn't exist
            if broker_name not in brokers_summary:
                brokers_summary[broker_name] = {
                    name: 0.0 for name in group_titles.values()
                }
                brokers_summary[broker_name]["Uncategorized"] = 0.0

            # Accumulate the total for the owner
            brokers_summary[broker_name][owner] += total
            logger.debug(f"Added ${total:,.2f} to {owner} under {broker_name}")

    return brokers_summary


def generate_broker_summary_embed(ctx, specific_broker=None):
    """Return a Discord embed summarizing holdings by owner for each broker."""

    brokers_summary = all_brokers_summary_by_owner(specific_broker)
    broker_label = (
        specific_broker.upper()
        if specific_broker and specific_broker.lower() in ["bbae", "dspac"]
        else specific_broker.capitalize() if specific_broker else "All Active Brokers"
    )

    embed = discord.Embed(title=f"**{broker_label} Summary**", color=discord.Color.blue())

    for broker_name, owner_totals in brokers_summary.items():
        account_owner_count = sum(
            len(accounts)
            for _group, accounts in ACCOUNT_MAPPING.get(broker_name, {}).items()
        )
        broker_total = sum(owner_totals.values())

        filtered_totals = {o: t for o, t in owner_totals.items() if t != 0}
        if not filtered_totals:
            continue

        broker_summary = f"({account_owner_count} Owner groups, Total: ${broker_total:,.2f})\n"
        for owner, total in filtered_totals.items():
            broker_summary += f"{owner}: ${total:,.2f}\n"

        formatted_name = (
            broker_name.upper()
            if broker_name.lower() in ["bbae", "dspac"]
            else broker_name.capitalize()
        )
        embed.add_field(name=formatted_name, value=broker_summary.strip(), inline=True)

        if specific_broker:
            break

    return embed


def aggregate_owner_totals():
    """Return total holdings aggregated by owner across all brokers."""

    summary = all_brokers_summary_by_owner()
    owner_totals = {}
    for broker_totals in summary.values():
        for owner, total in broker_totals.items():
            owner_totals[owner] = owner_totals.get(owner, 0.0) + total
    return owner_totals


def generate_owner_totals_embed():
    """Create a Discord embed showing aggregated holdings by owner."""

    owner_totals = aggregate_owner_totals()
    embed = discord.Embed(
        title="**Owner Totals Across Brokers**", color=discord.Color.blue()
    )
    for owner, total in sorted(owner_totals.items(), key=lambda x: x[1], reverse=True):
        embed.add_field(name=owner, value=f"${total:,.2f}", inline=True)
    return embed


def get_fennel_account_number(account_str):
    """Extract Fennel account number by combining the first and second number from the string."""
    parts = account_str.split()
    if len(parts) >= 4 and parts[0].lower() == "fennel":
        # Combine the first number and the second number to form account number
        newpart = parts[3].split(")")[0]
        account_number = parts[1] + newpart
        return account_number
    elif len(parts) >= 4 and parts[0].lower == "fidelity":
        newpart = parts[3].split(")")[0]
        account_number = parts[1] + newpart
        return account_number
    return account_str  # Default behavior for non-Fennel accounts


# Function to print lines from a file to Discord
async def print_to_discord(ctx, file_path="todiscord.txt", delay=1):
    """
    Reads a file line by line and sends each line as a message to Discord.
    Args:
        ctx: The context of the Discord command.
        file_path: The file to read and print to Discord.
        delay: The time (in seconds) to wait between sending each line.
    """
    try:
        # Open the file
        with open(file_path, "r") as file:
            # Read the file line by line
            for line in file:
                # Send each line to Discord
                await ctx.send(line.strip())

                # Delay between sending lines
                await asyncio.sleep(delay)
    except FileNotFoundError:
        await ctx.send(f"Error: The file {file_path} was not found.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


async def send_large_message_chunks(ctx, message):
    logger.warning("send_large_message_chunks is deprecated.")

    # Discord messages have a max character limit of 2000
    max_length = 2000

    # Split the message by line breaks
    lines = message.split("\n")

    current_chunk = ""
    for line in lines:
        # Check if adding the next line would exceed the character limit
        if (
            len(current_chunk) + len(line) + 1 > max_length
        ):  # +1 for the added newline character
            await ctx.send(current_chunk)  # Send the current chunk
            current_chunk = ""  # Reset the chunk

        # Add the line to the current chunk
        if current_chunk:
            current_chunk += "\n" + line
        else:
            current_chunk = line

    # Send any remaining text in the current chunk
    if current_chunk:
        await ctx.send(current_chunk)


def get_order_details(broker, account_number, ticker):
    """# Search orders_log.csv for matching broker, account, and stock ticker.
    try:
        logger.debug(f"Querying orders for {broker} {account_number} {ticker}")
        with open(ORDERS_CSV_FILE, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:


                # Handle Fennel specific account number parsing
                if broker.lower() == 'fennel':
                    account_in_csv = get_fennel_account_number(row['Account Number'])
                elif broker.lower() == 'fidelity':
                    fidelity_account = get_fennel_account_number(row['Account Number'])
                else:
                    account_in_csv = row['Account Number'][-4:]  # Last 4 digits for non-Fennel accounts

                if row['Broker Name'] == broker and account_in_csv == account_number and row['Stock'].upper() == ticker:
                    action = row['Order Type'].capitalize()
                    quantity = row['Quantity']
                    timestamp = row['Date']
                    return f"{action} {quantity} {ticker} {timestamp}"
        return None
    except FileNotFoundError:
        return None
    except KeyError as e:
        raise KeyError(f"Missing expected column in orders_log.csv: {e}")
    """


# -- DEV Functions


def update_file_version(config_path, new_version):
    """
    Update the file_version in the given YAML configuration file.

    Args:
        config_path (str or Path): Path to the YAML configuration file.
        new_version (str): The new file version to set.
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Load the current YAML data
    with open(config_path, "r") as file:
        config_data = yaml.safe_load(file)

    # Update the file_version
    config_data["general_settings"]["file_version"] = new_version

    # Save the updated YAML data back to the file
    with open(config_path, "w") as file:
        yaml.safe_dump(config_data, file)

    logging.info(f"Updated file_version to {new_version} in {config_path}")


def get_file_version(config_path):
    """
    Retrieves the current file version from the configuration file.

    Args:
        config_path (str): Path to the settings.yaml file.

    Returns:
        str: Current file version if successful, None otherwise.
    """
    try:
        with open(config_path, "r") as file:
            config = yaml.safe_load(file)
            return config.get("general_settings", {}).get("file_version")
    except Exception as e:
        logging.error(f"Failed to get file version: {e}")
        return None
