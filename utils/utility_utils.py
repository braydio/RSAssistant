import asyncio
import csv
import json
import logging
import os
from datetime import datetime, timedelta
import discord
import warnings
import functools

from utils.config_utils import (get_account_nickname, load_account_mappings,
                                load_config)


# Load configuration and holdings data
config = load_config()
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']
MANUAL_ORDER_ENTRY_TXT = config['paths']['manual_orders']

def get_latest_timestamp_from_holdings(filename):
    """Reads the latest timestamp from the specified CSV file."""
    try:
        with open(filename, mode='r') as file:
            reader = csv.DictReader(file)
            rows = list(reader)  # Load all rows to get the last timestamp
            if rows:
                return rows[-1].get("Timestamp", "Timestamp not available")
            else:
                return "No entries in CSV"
    except FileNotFoundError:
        return "CSV file not found"

HOLDINGS_TIMESTAMP = get_latest_timestamp_from_holdings(HOLDINGS_LOG_CSV)

def deprecated(reason=None):
    """
    A decorator to mark functions as deprecated.

    Parameters:
    - reason (str): Optional. A message providing details on the deprecation reason or alternative function.

    Usage:
    @deprecated("Use 'new_function' instead.")
    def old_function():
        pass
    """
    def decorator(func):
        message = f"The function '{func.__name__}' is deprecated."
        if reason:
            message += f" {reason}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(
                message,
                category=DeprecationWarning,
                stacklevel=2
            )
            return func(*args, **kwargs)
        
        return wrapper

    return decorator

# -- BROKERWITH TICKER Command

async def track_ticker_summary(ctx, ticker, show_details=False, specific_broker=None, holding_logs_file=HOLDINGS_LOG_CSV, account_mapping_file=ACCOUNT_MAPPING_FILE):
    """
    Track accounts that hold the specified ticker, aggregating at the broker level.
    Shows details at the account level if a specific broker is provided.
    """
    holdings = {}
    ticker = ticker.upper().strip()  # Standardize ticker format

    # Load account mappings
    account_mapping = load_account_mappings(account_mapping_file)

    try:
        # Read holdings log
        with open(holding_logs_file, mode='r') as file:
            csv_reader = csv.DictReader(file)

            for row in csv_reader:
                account_key = row['Key']  # "Broker Name + Nickname"
                stock = row['Stock'].upper().strip()  # Standardize stock symbol

                # Parse quantity, price, and account total
                try:
                    quantity = float(row['Quantity'])
                    price = float(row['Price'])
                    account_total = float(row['Account Total'])
                except ValueError:
                    continue  # Skip rows where Quantity, Price, or Account Total are invalid

                broker_name = row['Broker Name']

                # Initialize broker in holdings if not present
                if broker_name not in holdings:
                    holdings[broker_name] = {}

                # Store detailed data in a dictionary
                if stock == ticker and quantity > 0:
                    holdings[broker_name][account_key] = {
                        "status": "✅",
                        "Quantity": quantity,
                        "Price": price,
                        "Account Total": account_total
                    }
                else:
                    # Only set to "❌" if not already marked as holding, to avoid overwriting
                    if account_key not in holdings[broker_name]:
                        holdings[broker_name][account_key] = {
                            "status": "❌",
                            "Quantity": "N/A",
                            "Price": "N/A",
                            "Account Total": "N/A"
                        }

        # Decide which view to show based on the specific_broker argument
        if specific_broker:
            await get_detailed_broker_view(ctx, ticker, specific_broker, holdings, account_mapping)
        else:
            await get_aggregated_broker_summary(ctx, ticker, holdings, account_mapping)

    except FileNotFoundError:
        await ctx.send(f"Error: The file {holding_logs_file} or {account_mapping_file} was not found.")
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
        color=discord.Color.blue()
    )

    for broker_name, group_data in account_mapping.items():
        if isinstance(group_data, dict):
            # Count the total accounts and held accounts for each broker
            total_accounts = 0
            held_accounts = 0
            
            for group_number, accounts in group_data.items():
                if isinstance(accounts, dict):
                    total_accounts += len(accounts)  # Add all accounts under the broker to total count
                    for account_number, account_nickname in accounts.items():
                        account_key = f"{broker_name} {account_nickname}"
                        # Check if the account is marked as holding the ticker
                        if holdings.get(broker_name, {}).get(account_key, {}).get("status") == "✅":
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
                inline=True
            )

    # Add footer with timestamp
    embed.set_footer(text=f"Try: '..brokerwith {ticker} <broker>' for details. • {HOLDINGS_TIMESTAMP}")
    await ctx.send(embed=embed)

async def get_detailed_broker_view(ctx, ticker, specific_broker, holdings, account_mapping):
    """
    Organizes the detailed view for a specific broker, calling separate functions to display:
    - Accounts holding the position.
    - Accounts not holding the position.
    """
    broker_name = specific_broker.capitalize()
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
                            account_total = f"${float(account_entry.get('Account Total', 0)):,.2f}"
                        except (ValueError, TypeError):
                            price, account_total = "$0.00", "$0.00"
                        accounts_with_position.append((account_nickname, account_number[-4:], quantity, price, account_total))
                    else:
                        # Account does not hold the ticker
                        accounts_without_position.append((account_nickname, account_number[-4:]))
        
        # Send embeds for accounts with and without position
        await send_accounts_with_position_embed(ctx, broker_name, ticker, accounts_with_position)
        await send_accounts_without_position_embed(ctx, broker_name, ticker, accounts_without_position)
    else:
        await ctx.send(f"No broker found for {broker_name}.")

async def send_accounts_with_position_embed(ctx, broker_name, ticker, accounts_with_position):
    """
    Creates and sends an embed for accounts that hold the ticker position.
    """
    if accounts_with_position:
        # Embed for accounts with the position
        embed_with_position = discord.Embed(
            title=f"{broker_name} Account Holdings {ticker}",
            color=discord.Color.green()
        )
        # Add account details for each holding position
        for nickname, last_four, quantity, price, account_total in accounts_with_position:
            embed_with_position.add_field(
                name=f"{nickname} ✅",
                value=(
                    f"Account: {last_four}\n"
                    f"Quantity: {quantity}\n"
                    f"Price: {price}\n"
                    f"Account Total: {account_total}"
                ),
                inline=True
            )
        # Add footer with the timestamp from HOLDINGS_TIMESTAMP
        embed_with_position.set_footer(text=f"Detailed holdings for {ticker} • {HOLDINGS_TIMESTAMP}")
        await ctx.send(embed=embed_with_position)
    else:
        # Embed indicating no holdings
        embed_with_position = discord.Embed(
            title=f"{broker_name} Account Holdings {ticker}",
            description="No accounts hold this position",
            color=discord.Color.red()
        )
        embed_with_position.set_footer(text=HOLDINGS_TIMESTAMP)
        await ctx.send(embed=embed_with_position)

async def send_accounts_without_position_embed(ctx, broker_name, ticker, accounts_without_position):
    """
    Creates and sends an embed for accounts that do not hold the ticker position.
    """
    if accounts_without_position:
        # Create an embed for accounts without the position
        embed_without_position = discord.Embed(
            title=f"{broker_name} Accounts Not Holding {ticker}",
            color=discord.Color.blue()
        )
        # Add each account that does not hold the position
        for nickname, last_four in accounts_without_position:
            embed_without_position.add_field(
                name=f"{nickname} ❌",
                value=f"Account: {last_four}\nNo position in {ticker}",
                inline=True
            )
        # Add footer with the timestamp from HOLDINGS_TIMESTAMP
        embed_without_position.set_footer(text=f"Accounts without holdings for {ticker} • {HOLDINGS_TIMESTAMP}")
        await ctx.send(embed=embed_without_position)
    else:
        # Optional embed if all accounts hold the position (for cases where there are no non-holding accounts)
        embed_without_position = discord.Embed(
            title=f"{broker_name} Accounts Not Holding {ticker}",
            description="All accounts hold this position",
            color=discord.Color.green()
        )
        embed_without_position.set_footer(text=HOLDINGS_TIMESTAMP)
        await ctx.send(embed=embed_without_position)

# --

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

def get_order_details(broker, account_number, ticker):
    """Search orders_log.csv for matching broker, account, and stock ticker."""
    try:
        print(broker, ticker, account_number)
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


# Function to print lines from a file to Discord
async def print_to_discord(ctx, file_path=MANUAL_ORDER_ENTRY_TXT, delay=1):
    """
    Reads a file line by line and sends each line as a message to Discord.
    Args:
        ctx: The context of the Discord command.
        file_path: The file to read and print to Discord.
        delay: The time (in seconds) to wait between sending each line.
    """
    try:
        # Open the file
        with open(file_path, 'r') as file:
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
    # Discord messages have a max character limit of 2000
    print(" Brayden need to move this to config_utils.")
    max_length = 2000

    # Split the message by line breaks
    lines = message.split('\n')
    
    current_chunk = ""
    for line in lines:
        # Check if adding the next line would exceed the character limit
        if len(current_chunk) + len(line) + 1 > max_length:  # +1 for the added newline character
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
    
    print(" Brayden need to move this to config_utils.")