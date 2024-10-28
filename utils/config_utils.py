import csv
import json
import logging
import os
import yfinance as yf
from datetime import datetime

import discord
import yaml

CONFIG_PATH = 'config/settings.yaml'

def load_config(config_path=CONFIG_PATH):
    """Loads the YAML config file and returns it as a dictionary."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with open(config_path, 'r') as config_file:
        config = yaml.safe_load(config_file)

    # Load environment variables if needed
    config['discord']['token'] = os.getenv('DISCORD_TOKEN', config['discord'].get('token'))

    return config

# Load the configuration (make sure the config is loaded before accessing its keys)
config = load_config()

# Paths loaded from the config
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
MANUAL_ORDER_ENTRY_TXT = config['paths']['manual_orders']
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
WATCHLIST_FILE = config['paths']['watch_list']
EXCLUDED_BROKERS = config.get('excluded_brokers', {})


# -- Mapping Config

def load_account_mappings(filename=ACCOUNT_MAPPING_FILE):
    """Loads account mappings from the JSON file."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {filename}: {e}")
            return {}
    else:
        logging.error(f"Account mapping file {filename} not found.")
        return {}

def should_skip(broker, account_nickname):
    print(f'should_skip called {broker} and {account_nickname} but this is being deprecated.')
    """Returns True if the broker and account_nickname should be skipped."""
    # if EXCLUDED_BROKERS is None:
    #     # If EXCLUDED_BROKERS is None, treat it as an empty dictionary
    #     return False

    # if broker in EXCLUDED_BROKERS and account_nickname in EXCLUDED_BROKERS[broker]:
    #     return True

    # return False

def get_account_nickname(broker, group_number, account_number):
    """
    Retrieves the account nickname from the account mapping,
    or returns the account number if the mapping is not found.
    """
    account_mapping = load_account_mappings()

    if not account_mapping:
        logging.error("Account mappings are empty or not loaded.")
        return account_number

    # Ensure account_number is padded to 4 digits
    padded_account_number = str(account_number).zfill(4)

    # Get the broker data
    broker_accounts = account_mapping.get(broker, {})

    if not broker_accounts:
        logging.warning(f"No account mappings found for broker: {broker}. Returning account number.")
        return padded_account_number

    # Get the group data
    group_accounts = broker_accounts.get(group_number, {})

    if not group_accounts:
        logging.warning(f"No account mappings found for broker: {broker} and group number: {group_number}.")
        return padded_account_number

    # Get the account nickname or return the padded account number if not found
    return group_accounts.get(padded_account_number, padded_account_number)
    
def save_account_mappings(mappings):
    """Save the account mappings to the JSON file."""
    with open(ACCOUNT_MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=4)

account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)

# -- Account Indexing and Commands

async def all_brokers(ctx, filename=ACCOUNT_MAPPING_FILE):
    """
    Returns a list of active brokers based on the updated account mapping structure, 
    with each embed containing up to 9 brokers.
    """
    try:
        # Load account mappings from the JSON file synchronously
        with open(filename, 'r') as f:
            data = f.read()

            # Check if the file is empty
            if not data.strip():
                await ctx.send("Error: Account mapping file is empty.")
                return

            # Parse JSON data
            account_mapping = json.loads(data)

            # Ensure account_mapping is a valid dictionary
            if not isinstance(account_mapping, dict):
                await ctx.send("Error: Account mapping is not valid.")
                return

        active_brokers = list(account_mapping.keys())
        chunk_size = 9  # Maximum number of brokers per embed
        total_brokers = len(active_brokers)

        for i in range(0, total_brokers, chunk_size):
            embed = discord.Embed(
                title="**Active Brokers**",
                description="",
                color=discord.Color.blue()
            )
            chunk_brokers = active_brokers[i:i+chunk_size]

            for broker in chunk_brokers:
                # Ensure broker_data is valid
                broker_data = account_mapping.get(broker)
                if broker_data is None:
                    await ctx.send(f"Error: Broker '{broker}' has no data (None).")
                    continue
                
                if not isinstance(broker_data, dict):
                    await ctx.send(f"Error: Broker '{broker}' data is not in the expected format.")
                    continue

                total_holdings = 0
                account_count = 0

                # Iterate through each group under the broker
                for group_number, accounts in broker_data.items():
                    # Sum account totals for each group
                    group_account_count, group_total = sum_account_totals(broker, group_number, accounts)
                    account_count += group_account_count
                    total_holdings += group_total

                # Prepare broker's information for display
                plural_check = "account" if account_count == 1 else "accounts"
                embed.add_field(
                    name=broker,
                    value=(f"{account_count} {plural_check}\nTotal: ${total_holdings:,.2f}"),
                    inline=True
                )

            embed.set_footer(text="Try: '..brokerlist <broker>' to list accounts.")
            await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"Error loading account mappings: {e}")
        print(f"Exception: {e}")

def get_account_totals(broker, group_number=None, account_number=None):
    """
    Retrieve the account totals for all accounts under the specified broker, group, and account from holdings_log.csv.
    
    Parameters:
    - broker: The broker for which to get account totals.
    - group_number: The group number to filter accounts (optional).
    - account_number: The account number to filter accounts (optional).
    
    Returns:
    - A dictionary with account numbers as keys and their total as values.
    """
    account_totals = {}

    with open(HOLDINGS_LOG_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            # Match broker name (case-insensitive)
            if row['Broker Name'].lower() == broker.lower():
                
                # Optionally filter by group number if provided
                if group_number and row['Broker Number'] != str(group_number):
                    continue  # Skip if group number doesn't match

                # Optionally filter by account number if provided
                if account_number and row['Account Number'] != str(account_number):
                    continue  # Skip if account number doesn't match

                # Add the account number and its total to the dictionary
                account_totals[row['Account Number']] = float(row['Account Total'])
    
    return account_totals

def sum_account_totals(broker, group_number, accounts):
    """
    Sum the 'Account Total' for all accounts under a specific broker and group number
    from the holdings_log.csv file.
    
    Parameters:
    - broker: The broker for which to sum account totals.
    - group_number: The group number under the broker.
    - accounts: A dictionary of account numbers and their nicknames.
    
    Returns:
    - A tuple with the total number of accounts and the sum of all account totals for the broker and group.
    """
    total_sum = 0.0
    account_count = 0

    # Get the totals for each account in the group
    account_totals = get_account_totals(broker, group_number)

    # Sum the totals of all accounts in the group
    for account_number in accounts.keys():
        if account_number in account_totals:
            total_sum += account_totals[account_number]
            account_count += 1

    return account_count, total_sum


def calculate_broker_totals(account_mapping):
    """
    Calculate and display the total number of accounts and the total holdings for each broker and group.
    
    Parameters:
    - account_mapping: The account mappings loaded from account_mapping.json.
    
    Returns:
    - A dictionary with broker and group totals.
    """
    broker_totals = {}

    # Iterate through brokers in the account mapping
    for broker, groups in account_mapping.items():
        broker_totals[broker] = {}

        # Iterate through each group under the broker
        for group_number, accounts in groups.items():
            account_count, total_holdings = sum_account_totals(broker, accounts)

            # Store the result for this broker and group number
            broker_totals[broker][group_number] = {
                'account_count': account_count,
                'total_holdings': total_holdings
            }

    return broker_totals


def all_broker_accounts(broker):
    """
    Retrieve all accounts (nicknames and numbers) for a given broker.
    
    Parameters:
    - broker: The broker for which to retrieve accounts.
    
    Returns:
    - A list of account dictionaries or an error message if the broker is not found.
    """
    mappings = load_account_mappings()

    # Check if the broker exists
    if broker not in mappings:
        return f"Broker '{broker}' not found. Available brokers: {all_brokers()}"
    
    # Get the accounts for the broker
    accounts = mappings[broker].get('accounts', [])
    
    if not accounts:
        return f"No accounts found for broker '{broker}'."
    
    return accounts


async def all_account_nicknames(ctx, broker):
    """
    Retrieve all account nicknames for a given broker, including group numbers.
    
    Parameters:
    - broker: The broker for which to retrieve account nicknames.
    
    Returns:
    - A list of nicknames or an error message if the broker is not found.
    """
    # Load the account mappings
    mappings = load_account_mappings()
    broker_lower = broker.lower()
    
    # Normalize broker names to lowercase for case-insensitive comparison
    normalized_mappings = {key.lower(): key for key in mappings}

    # Check if the broker exists in the mappings
    if broker_lower not in normalized_mappings:
        available_brokers = ', '.join(mappings.keys())
        await ctx.send(f"Broker {broker} not found. Available brokers: {available_brokers}")
        return
    
    # Retrieve the original broker name and its groups
    original_broker = normalized_mappings[broker_lower]
    broker_groups = mappings[original_broker]

    # Sum total holdings across all accounts for this broker
    total_sum = 0
    for group_number, accounts in broker_groups.items():
        for account_number in accounts.keys():
            total_sum += sum_account_totals(original_broker, group_number, account_number)

    # Prepare the embed message to show all accounts and their totals
    embed = discord.Embed(
        title=f"**{original_broker}**",
        description=f"All active accounts. Total Holdings: ${total_sum:,.2f}",
        color=discord.Color.blue()
    )

    # Iterate over the groups and accounts under each group
    for group_number, accounts in broker_groups.items():
        account_totals = get_account_totals(original_broker, group_number)
        
        # Loop through each account in the group
        for account_number, nickname in accounts.items():
            total = account_totals.get(account_number, 0.0)  # Get total, default to 0 if not found
            embed.add_field(
                name=f"{group_number} - {nickname}",
                value=f"Total: ${total:,.2f}",
                inline=True
            )

    # Send the embed with all account nicknames and totals
    await ctx.send(embed=embed)


def all_account_numbers(broker):
    """
    Retrieve all account numbers for a given broker.
    
    Parameters:
    - broker: The broker for which to retrieve account numbers.
    
    Returns:
    - A list of account numbers or an error message if the broker is not found.
    """
    accounts = all_broker_accounts(broker)
    
    # If accounts is a string, it's an error message
    if isinstance(accounts, str):
        return accounts
    
    # Return the account numbers
    account_numbers = [account['account_number'] for account in accounts]
    return account_numbers if account_numbers else f"No account numbers found for broker '{broker}'."

# -- Helper functions

def get_last_stock_price(stock):
    """
    Fetches the last price of the given stock using Yahoo Finance.
    """
    try:
        ticker = yf.Ticker(stock)
        stock_info = ticker.history(period="1d")
        if not stock_info.empty:
            last_price = stock_info['Close'].iloc[-1]
            return round(last_price, 2)  # Round to 2 decimal places for simplicity
            
        else:
            logging.warning(f"No stock data found for {stock}.")
            return None
    except Exception as e:
        logging.error(f"Error fetching last price for {stock}: {e}")
        return None

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

def account_totals_by_group_number(broker):
    """
    Retrieve and sum account totals for a broker, categorized by the indicator in the nickname (from settings.yaml).
    
    Parameters:
    - broker: The broker for which to get account totals.
    
    Returns:
    - A dictionary with totals categorized by group titles from settings.yaml.
    """
    # Load group titles from settings.yaml
    group_titles = config.get('account_owners', {})

    # Initialize totals for each category found in settings.yaml
    totals = {title: 0.0 for title in group_titles}
    # Add a 'None' category if not present in the YAML, as a fallback
    if 'None' not in totals:
        totals['None'] = 0.0

    # Track unique account numbers that have already been processed
    processed_accounts = set()

    # Open the holdings log file and read its contents
    with open(HOLDINGS_LOG_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        
        # Loop through each row in the CSV file
        for row in reader:
            if row['Broker Name'].lower() == broker.lower():
                account_number = row['Account']
                total = float(row['Account Total'])

                # Skip this account if it has already been processed
                if account_number in processed_accounts:
                    continue
                
                # Mark this account as processed
                processed_accounts.add(account_number)
                
                # Check the nickname in account_mapping.json and categorize
                nickname = account_mapping[broker].get(account_number, "")
                
                # Assign totals based on group titles from settings.yaml
                categorized = False
                for title in group_titles:
                    if f"({title})" in nickname:
                        totals[title] += total
                        categorized = True
                        break
                
                # If no group title is found in the nickname, categorize it as 'None'
                if not categorized:
                    totals["None"] += total
    
    return totals

async def all_brokers_groups(ctx, filename=ACCOUNT_MAPPING_FILE):
    """
    Returns a list of active brokers based on the account mapping file.
    Breaks down accounts by (Dre), (Lem), and those with no indicator.
    """
    # Load the account mapping file
    with open(filename, 'r') as f:
        global account_mapping  # Make account_mapping global for access in the other function
        account_mapping = json.load(f)

        active_brokers = list(account_mapping.keys())

        # Create the embed
        embed = discord.Embed(
            title="**All Active Brokers**",
            description="",
            color=discord.Color.blue()
        )

        # Loop through active brokers and add them as fields in the embed
        for broker in active_brokers:
            account_count = len(account_mapping[broker])
            plural_check = "account" if account_count == 1 else "accounts"

            # Get totals by indicator (Dre, Lem, None)
            totals_by_indicator = account_totals_by_group_number(broker)

            # Add the broker and totals to the embed
            embed.add_field(
                name=f"{broker} ({account_count} {plural_check})",
                value=(
                    f"Dre: ${totals_by_indicator['Dre']:,.2f}\n"
                    f"Lizzy: ${totals_by_indicator['Lem']:,.2f}\n"
                    f"Brayden: ${totals_by_indicator['None']:,.2f}"
                ),
                inline=True
            )

        # Set footer message
        embed.set_footer(text="Try: '..brokerlist <broker>' to list accounts.")

        # Send the embed message
        await ctx.send(embed=embed)

# -- Deprecated functions

def add_account(broker, account_number, account_nickname):
    print(f"add_account called for {broker}{account_number}{account_nickname} but this function is deprecated.")
