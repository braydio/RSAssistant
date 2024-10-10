import asyncio
import json
import logging
from datetime import datetime, timedelta
import csv
import os
from utils.config_utils import load_config, load_account_mappings, get_account_nickname
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

async def track_ticker_summary(ctx, ticker, show_details=False, holding_logs_file=HOLDINGS_LOG_CSV, account_mapping_file=ACCOUNT_MAPPING_FILE):
    holdings = {}
    no_holdings = {}
    unique_accounts = {}
    ticker = ticker.upper()

    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)

    try:
        with open(account_mapping_file, 'r') as am_file:
            account_mapping = json.load(am_file)

        # Open the holdings log
        with open(holding_logs_file, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                broker_name = row['Broker Name']
                account = row['Account']

                # Handle Fennel specific account number parsing
                if broker_name.lower() == 'fennel':
                    account = get_fennel_account_number(account)
                else:
                    account = account[-4:]  # Last 4 digits for non-Fennel accounts

                stock = row['Stock'].upper()
                quantity = float(row['Quantity'])

                if broker_name not in holdings:
                    holdings[broker_name] = set()
                    no_holdings[broker_name] = set()
                    unique_accounts[broker_name] = set()

                unique_accounts[broker_name].add(account)

                if stock == ticker and quantity > 0:
                    holdings[broker_name].add(account)
                else:
                    no_holdings[broker_name].add(account)

        message = f"**{ticker} Holdings - All Brokerages**\n**=============================**\n"
        for broker, accounts in account_mapping.items():
            total = len(accounts)
            held_accounts = len(holdings.get(broker, []))
            message += f"**| ** {broker} - Position in {held_accounts} of {total} accounts\n"

        if show_details:
            message += "\n**Ticker not in the following accounts:**\n"
            for broker, accounts in no_holdings.items():
                if accounts:
                    message += f"\n**{broker}**:\n"
                    for account in accounts:
                        account_nickname = get_account_nickname(broker, account)
                        logging.info(account_nickname)
                        # Check for matching orders in orders_log.csv
                        order_details = get_order_details(broker, account, ticker)
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
