import csv
import json
import logging
import os
import asyncio
import discord
import yaml
import yfinance as yf
from datetime import datetime

CONFIG_PATH = 'config/settings.yaml'

# Load and validate configuration
def load_config(config_path=CONFIG_PATH):
    """Loads the YAML config file and returns it as a dictionary."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with open(config_path, 'r', encoding='utf-8') as config_file:
        config = yaml.safe_load(config_file)

    config['discord']['token'] = os.getenv('DISCORD_TOKEN', config['discord'].get('token'))
    return config

# Load the configuration (make sure the config is loaded before accessing its keys)
config = load_config()
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
MANUAL_ORDER_ENTRY_TXT = config['paths']['manual_orders']
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
WATCHLIST_FILE = config['paths']['watch_list']
EXCLUDED_BROKERS = config.get('excluded_brokers', {})
ACCOUNT_OWNERS = config.get('account_owners', {})

# Account Mapping / Nicknames

def load_account_mappings(filename=ACCOUNT_MAPPING_FILE):
    """Loads account mappings from the JSON file and ensures the data structure is valid."""
    if not os.path.exists(filename):
        logging.error(f"Account mapping file {filename} not found.")
        return {}

    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)

            if not isinstance(data, dict):
                logging.error(f"Invalid account mapping structure in {filename}.")
                return {}

            for broker, broker_data in data.items():
                if not isinstance(broker_data, dict):
                    logging.error(f"Invalid data for broker '{broker}'.")
                    continue

                for group, accounts in broker_data.items():
                    if not isinstance(accounts, dict):
                        logging.error(f"Invalid group structure for '{group}' in broker '{broker}'.")
                        broker_data[group] = {}

            return data

    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {filename}: {e}")
        return {}
  
def save_account_mappings(mappings):
    """Save the account mappings to the JSON file."""
    with open(ACCOUNT_MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, indent=4)

account_mapping = load_account_mappings()

def get_account_nickname(broker, group_number, account_number):
    """
    Retrieves the account nickname from the account mapping,
    or returns the account number if the mapping is not found.
    """
    account_mapping = load_account_mappings()

    account_number_str = str(account_number)
    group_number_str = str(group_number)
    broker_accounts = account_mapping.get(broker, {})

    if not broker_accounts:
        logging.warning(f"No account mappings found for broker: {broker}.")
        return account_number_str

    group_accounts = broker_accounts.get(group_number_str, {})
    return group_accounts.get(account_number_str, account_number_str)

# -- Account Indexing and Commands

# Discord Command: Display Active Brokers
async def all_brokers(ctx):
    try:
        active_brokers = list(account_mapping.keys())
        chunk_size = 9
        for i in range(0, len(active_brokers), chunk_size):
            embed = discord.Embed(title="**Active Brokers**", color=discord.Color.blue())
            chunk_brokers = active_brokers[i:i + chunk_size]
            for broker in chunk_brokers:
                broker_data = account_mapping.get(broker)
                if not isinstance(broker_data, dict):
                    await ctx.send(f"Error: Broker '{broker}' has invalid data.")
                    continue

                total_holdings, account_count = 0, 0
                for group_number, accounts in broker_data.items():
                    try:
                        group_account_count, group_total = sum_account_totals(broker, group_number, accounts)
                        account_count += group_account_count
                        total_holdings += group_total
                    except ValueError as ve:
                        logging.error(f"Value error for broker {broker}, group {group_number}: {ve}")
                        continue
                
                embed.add_field(name=broker, value=f"{account_count} accounts\nTotal: ${total_holdings:,.2f}", inline=True)

            await ctx.send(embed=embed)
            await asyncio.sleep(1)

    except Exception as e:
        await ctx.send(f"An error occurred: {e}")
        logging.error(f"Exception in all_brokers: {e}")

# Retrieve Last Stock Price
def get_last_stock_price(stock):
    """Fetches the last price of a given stock using Yahoo Finance."""
    try:
        ticker = yf.Ticker(stock)
        stock_info = ticker.history(period="1d")
        if not stock_info.empty:
            return round(stock_info['Close'].iloc[-1], 2)
        logging.warning(f"No stock data found for {stock}.")
        return None
    except Exception as e:
        logging.error(f"Error fetching last price for {stock}: {e}")
        return None

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

    with open(HOLDINGS_LOG_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Broker Name'].lower() == broker.lower():
                if group_number and row['Broker Number'] != str(group_number):
                    continue
                if account_number and row['Account Number'] != str(account_number):
                    continue
                account_totals[row['Account Number']] = float(row['Account Total'])
    
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
                logging.warning(f"Account total for '{account_number}' is not a valid number.")
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
            account_count, total_holdings = sum_account_totals(broker, group_number, accounts)
            broker_totals[broker][group_number] = {
                'account_count': account_count,
                'total_holdings': total_holdings
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
        return f"Broker '{broker}' not found. Available brokers: {list(mappings.keys())}"
    return mappings[broker].get('accounts', [])

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
        available_brokers = ', '.join(mappings.keys())
        await ctx.send(f"Broker {broker} not found. Available brokers: {available_brokers}")
        return

    original_broker = normalized_mappings[broker_lower]
    broker_groups = mappings[original_broker]
    total_sum = sum(sum_account_totals(original_broker, group, accounts)[1] for group, accounts in broker_groups.items())

    embed = discord.Embed(
        title=f"**{original_broker}**",
        description=f"All active accounts. Total Holdings: ${total_sum:,.2f}",
        color=discord.Color.blue()
    )

    for group_number, accounts in broker_groups.items():
        account_totals = get_account_totals(original_broker, group_number)
        for account_number, nickname in accounts.items():
            total = account_totals.get(account_number, 0.0)
            embed.add_field(
                name=f"{group_number} - {nickname}",
                value=f"Total: ${total:,.2f}",
                inline=True
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
    return [account['account_number'] for account in accounts]

def all_brokers_summary_by_owner(config, account_mapping, specific_broker=None):
    """
    Summarizes account totals for each broker, grouped by account owner.

    Parameters:
        config (dict): Configuration with paths and account owners.
        account_mapping (dict): Mapping of accounts from JSON.
        specific_broker (str, optional): If provided, only summarize for this broker.

    Returns:
        dict: Dictionary with each broker’s total holdings grouped by owner.
    """
    group_titles = config.get('account_owners', {})
    brokers_summary = {}

    # Debug: Print the structure of account_mapping
    print("\nAccount Mapping Structure:")
    for broker, broker_data in account_mapping.items():
        print(f"{broker}: {broker_data}")

    processed_accounts = set()  # Track processed accounts to avoid duplicates

    with open(HOLDINGS_LOG_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            broker_name = row['Broker Name']
            if specific_broker and broker_name.lower() != specific_broker.lower():
                continue  # Skip if we're filtering by a specific broker

            account_number = row['Account Number']
            if (broker_name, account_number) in processed_accounts:
                print(f"Skipping duplicate entry for {broker_name}, Account Number: {account_number}")
                continue  # Skip if this account has already been processed

            total_str = row['Account Total'].strip()

            # Skip empty or invalid account total values
            try:
                total = float(total_str) if total_str else 0.0
            except ValueError:
                print(f"Skipping invalid total in row: {row}")
                continue

            # Mark this account as processed
            processed_accounts.add((broker_name, account_number))

            # Debug: Print account lookup details
            print(f"\nProcessing Broker: {broker_name}, Account Number: {account_number}")

            nickname = ""
            if broker_name in account_mapping:
                for broker_number, accounts in account_mapping[broker_name].items():
                    if account_number in accounts:
                        nickname = accounts[account_number]
                        break

            print(f"Fetched Nickname: '{nickname}'")

            if not nickname:
                print(f"No nickname found for Broker: {broker_name}, Account Number: {account_number}")

            owner = "Uncategorized"  # Default to Uncategorized
            matched = False

            # Match the owner based on account_owners' indicators in the nickname
            for indicator, owner_name in group_titles.items():
                print(f"Checking if '{indicator}' in nickname '{nickname}'...")
                if indicator in nickname:
                    owner = owner_name
                    matched = True
                    print(f"Match found! Indicator: '{indicator}' -> Owner: {owner}")
                    break
                else:
                    print(f"No match for indicator '{indicator}' in nickname '{nickname}'.")

            # Initialize broker in summary if it doesn't exist
            if broker_name not in brokers_summary:
                brokers_summary[broker_name] = {name: 0.0 for name in group_titles.values()}
                brokers_summary[broker_name]["Uncategorized"] = 0.0

            # Accumulate the total for the owner
            brokers_summary[broker_name][owner] += total
            print(f"Added ${total:,.2f} to {owner} under {broker_name}")

    return brokers_summary

def generate_broker_summary_embed(config, account_mapping, broker_name=None):
    """
    Generates a Discord embed for account owner summaries.

    Parameters:
        config (dict): Configuration dictionary.
        account_mapping (dict): Account mappings dictionary.
        broker_name (str, optional): If provided, only show summary for this broker.

    Returns:
        discord.Embed: The generated embed with summaries by account owner.
    """
    brokers_summary = all_brokers_summary_by_owner(config, account_mapping, broker_name)
    if broker_name:
        broker = broker_name.upper() if broker_name.lower() in ['bbae', 'dspac'] else broker_name.capitalize()
    else:
        broker = 'All Active Brokers'
    
    embed_title = f"**{broker} Summary**"
    embed = discord.Embed(title=embed_title, color=discord.Color.blue())

    for broker, owner_totals in brokers_summary.items():
        account_count = len(account_mapping.get(broker, {}))
        broker_total = sum(owner_totals.values())  # Calculate the total holdings for the broker

        # Include broker total in the summary header
        broker_summary = f"({account_count} accounts, Total: ${broker_total:,.2f})\n"

        # Filter out zero-balance owners
        filtered_totals = {owner: total for owner, total in owner_totals.items() if total != 0}

        # Only add the broker field if there are owners with non-zero balances
        if filtered_totals:
            for owner, total in filtered_totals.items():
                broker_summary += f"{owner}: ${total:,.2f}\n"
            
            # Capitalize or adjust broker name if needed
            formatted_broker_name = broker.upper() if broker.lower() in ['bbae', 'dspac'] else broker.capitalize()
            embed.add_field(
                name=formatted_broker_name,
                value=broker_summary.strip(),  # Remove trailing newline
                inline=True
            )

            # Only show one broker if a specific one was requested
            if broker_name:
                break

    return embed

# -- Helper functions

# Send Large Messages in Chunks (Discord)
async def send_large_message_chunks(ctx, message):
    """Splits and sends a message in chunks if it exceeds Discord's character limit."""
    max_length = 2000
    lines = message.split('\n')
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            await ctx.send(current_chunk)
            current_chunk = ""
        current_chunk += "\n" + line if current_chunk else line
    if current_chunk:
        await ctx.send(current_chunk)