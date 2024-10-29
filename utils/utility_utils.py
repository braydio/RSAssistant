import asyncio
import csv
import json
import logging
import os
from datetime import datetime, timedelta
import discord

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
    Shows details at the account level if a specific broker is provided.
    """
    holdings = {}
    ticker = ticker.upper()

    # Load the account mappings from the new structure (brokers -> groups -> accounts)
    account_mapping = load_account_mappings(account_mapping_file)

    try:
        with open(holding_logs_file, mode='r') as file:
            csv_reader = csv.DictReader(file)

            for row in csv_reader:
                broker_name = row['Broker Name']
                account_number = row['Account Number']
                stock = row['Stock'].upper()
                quantity = float(row['Quantity'])

                # Handle Fennel-specific account parsing
                if broker_name.lower() == 'fennel':
                    account_number = get_fennel_account_number(account_number)
                else:
                    account_number = account_number[-4:]  # Last 4 digits for other brokers

                # Create broker key
                broker_key = broker_name

                # Initialize holdings for broker if not present
                if broker_key not in holdings:
                    holdings[broker_key] = {}

                # Track if the account holds the ticker
                if stock == ticker and quantity > 0:
                    holdings[broker_key][account_number] = "✅"
                else:
                    holdings[broker_key][account_number] = "❌"

        # Create a Discord embed message
        embed = discord.Embed(
            title=f"**{ticker} Holdings Summary**",
            description=f"All brokers summary, checking position for {ticker}.",
            color=discord.Color.blue()
        )

        # If a specific broker is provided, show detailed holdings for that broker
        if specific_broker:
            broker_name = specific_broker.capitalize()
            embed.title = f"**{ticker} - {broker_name} Holdings**"

            # Ensure that broker_name is a valid dictionary
            if broker_name in account_mapping:
                broker_data = account_mapping[broker_name]
                if isinstance(broker_data, dict):  # Ensure broker_data is a dictionary
                    for group_number, accounts in broker_data.items():
                        if isinstance(accounts, dict):  # Ensure accounts is a dictionary
                            for account_number, account_nickname in accounts.items():
                                status_icon = holdings.get(broker_name, {}).get(account_number[-4:], "❌")
                                embed.add_field(
                                    name=f"{account_nickname} {status_icon}",  # Icon next to nickname
                                    value=f"Account: {account_number[-4:]}",  # Shows the account number
                                    inline=True
                                )
                        else:
                            await ctx.send(f"Error: Expected accounts for group {group_number} to be a dictionary, but got {type(accounts)}")
                else:
                    await ctx.send(f"Error: Expected account mappings for {broker_name} to be a dictionary, but got {type(broker_data)}.")
            else:
                embed.description = f"No broker found for {broker_name}."
        else:
            # Aggregate behavior: Show all brokers with icons based on account positions
            for broker_name, group_data in account_mapping.items():
                if isinstance(group_data, dict):  # Check if group_data is a dictionary
                    total_accounts = sum(len(accounts) for accounts in group_data.values())
                    held_accounts = len([acc for acc in holdings.get(broker_name, {}).values() if acc == "✅"])

                    # Set the status icon based on the percentage of accounts holding the position
                    if held_accounts == total_accounts:
                        status_icon = "✅"  # All accounts hold the position
                    elif held_accounts == 0:
                        status_icon = "❌"  # No accounts hold the position
                    else:
                        status_icon = "🟡"  # Some accounts hold the position

                    embed.add_field(
                        name=f"{broker_name} {status_icon}",
                        value=f"Position in {held_accounts} of {total_accounts} accounts",
                        inline=True
                    )
                else:
                    await ctx.send(f"Error: Expected group data for {broker_name} to be a dictionary, got {type(group_data)}.")

        # Set the footer conditionally based on the `show_details` argument
        if show_details:
            embed.set_footer(text=f"Detailed view of {ticker}")
        else:
            embed.set_footer(text=f"Try: '..brokerwith {ticker} <broker>' for details.")

        # Send the embed message
        await ctx.send(embed=embed)

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