import asyncio
import csv
import json
import logging
import os
from datetime import datetime, timedelta

from utils.config_utils import (get_account_nickname, load_account_mappings,
                                load_config)
from utils.csv_utils import read_holdings_log

# Load configuration and holdings data
config = load_config()
holdings_data = read_holdings_log()
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']
MANUAL_ORDER_ENTRY_TXT = config['paths']['manual_orders']

async def profile(ctx, broker_name):
    """Generates a profile summary for a broker and sends it to Discord."""
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
    holdings_log = read_holdings_log(HOLDINGS_LOG_CSV)  # Load the holdings data

    broker_name = broker_name.capitalize()
    broker_accounts = account_mapping.get(broker_name, {})

    if not broker_accounts:
        await ctx.send(f"No accounts found for {broker_name}.")
        return

    # Initialize variables
    summary_message = []
    processed_accounts = set()
    total_holdings = 0

    for key, row in holdings_log.items():
        log_broker, account = key[:2]
        account_total = float(row[5])  # Convert to float

        if log_broker != broker_name or account in processed_accounts:
            continue

        processed_accounts.add(account)
        total_holdings += account_total
        summary_message.append(f"| Account: {account}: ${account_total:.2f}")

    # Add total holdings to the message
    summary_message.insert(0, f"{broker_name} - Broker Summary\n${total_holdings:.2f} in {len(processed_accounts)} Accounts \n===========================")

    # Send the summary message to Discord
    await send_large_message_chunks(ctx, "\n".join(summary_message))

async def track_ticker_summary(ctx, ticker, show_details=False, specific_broker=None, holding_logs_file=HOLDINGS_LOG_CSV, account_mapping_file=ACCOUNT_MAPPING_FILE):
    """
    Track which accounts hold or do not hold the specified ticker, aggregating at the broker level.
    Shows details at the account level if requested.
    """
    holdings = {}
    no_holdings = {}
    unique_accounts = {}
    ticker = ticker.upper()

    # Load the account mappings from the new structure (brokers -> groups -> accounts)
    account_mapping = load_account_mappings(account_mapping_file)

    try:
        with open(holding_logs_file, mode='r') as file:
            csv_reader = csv.DictReader(file)

            for row in csv_reader:
                broker_name = row['Broker Name']
                broker_number = row['Broker Number']
                account_number = row['Account Number']

                # Handle specific cases like Fennel (if custom account parsing is needed)
                if broker_name.lower() == 'fennel':
                    account_number = get_fennel_account_number(account_number)
                else:
                    account_number = account_number[-4:]  # Last 4 digits for other brokers

                stock = row['Stock'].upper()
                quantity = float(row['Quantity'])

                # Key is now the broker name only for broker-level aggregation
                broker_key = broker_name

                # Initialize the holding and no_holdings structures if not already present
                if broker_key not in holdings:
                    holdings[broker_key] = set()
                    no_holdings[broker_key] = set()
                    unique_accounts[broker_key] = set()

                unique_accounts[broker_key].add(account_number)

                # Track accounts holding the ticker
                if stock == ticker and quantity > 0:
                    holdings[broker_key].add(account_number)
                else:
                    no_holdings[broker_key].add(account_number)

        message = f"**{ticker} Holdings - All Brokerages**\n**=============================**\n"

        # Iterate through the account mapping (broker -> group -> accounts)
        for broker_name, groups in account_mapping.items():
            total_accounts = 0
            held_accounts = 0

            # Aggregate all groups under this broker
            for group_number, accounts in groups.items():
                total_accounts += len(accounts)
                held_accounts += len(holdings.get(broker_name, []))

            # Add summary for each broker
            message += f"**| ** {broker_name} - Position in {held_accounts} of {total_accounts} accounts\n"

            # If "details" mode is active and specific broker is provided, show account-level details
            if show_details and specific_broker and specific_broker.lower() == broker_name.lower():
                message += f"\n**Ticker not in the following accounts for {broker_name}:**\n"
                for account_number in no_holdings.get(broker_name, []):
                    account_nickname = get_account_nickname(broker_name, group_number, account_number)
                    order_details = get_order_details(broker_name, group_number, account_number, ticker)
                    if order_details:
                        message += f" **| <> ** {account_nickname} :  Found transaction data: \n   <-> *{order_details}*\n"
                    else:
                        message += f" **| <> ** {account_nickname}\n"

        await send_large_message_chunks(ctx, message)

    except FileNotFoundError:
        await ctx.send(f"Error: The file {holding_logs_file} or {account_mapping_file} was not found.")
    except KeyError as e:
        await ctx.send(f"Error: Missing expected column in CSV: {e}")
    except Exception as e:
        await ctx.send(f"Error: {e}")


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