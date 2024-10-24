import csv
import json
import logging
import os

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

account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)

def should_skip(broker, account_nickname):
    """Returns True if the broker and account_nickname should be skipped."""
    if broker in EXCLUDED_BROKERS and account_nickname in EXCLUDED_BROKERS[broker]:
        return True
    return False

def get_account_nickname(broker, group_number, account_number):
    """
    Retrieves the account nickname from the account mapping,
    or returns the account number if the mapping is not found.
    """
    account_mapping = load_account_mappings()

    if not account_mapping:
        logging.error("Account mappings are empty or not loaded.")
        return account_number

    # Get the broker data
    broker_accounts = account_mapping.get(broker, {})

    if not broker_accounts:
        logging.warning(f"No account mappings found for broker: {broker}. Returning account number.")
        return account_number

    # Get the group data
    group_accounts = broker_accounts.get(group_number, {})

    if not group_accounts:
        logging.warning(f"No account mappings found for broker: {broker} and group number: {group_number}.")
        return account_number

    # Get the account nickname or return the account number if not found
    return group_accounts.get(account_number, account_number)
    
def save_account_mappings(mappings):
    """Save the account mappings to the JSON file."""
    with open(ACCOUNT_MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=4)

# -- Account Indexing and Commands

import discord


async def all_brokers(ctx, filename=ACCOUNT_MAPPING_FILE):
    """
    Returns a list of active brokers based on the account mapping file, with each embed containing up to 6 accounts.
    """
    mappings = load_account_mappings()
    
    try:
        with open(filename, 'r') as f:
            account_mapping = json.load(f)

            active_brokers = list(account_mapping.keys())
            chunk_size = 6  # Maximum number of brokers per embed
            total_brokers = len(active_brokers)

            for i in range(0, total_brokers, chunk_size):
                embed = discord.Embed(
                    title="**Active Brokers**",
                    description="",
                    color=discord.Color.blue()
                )
                chunk_brokers = active_brokers[i:i+chunk_size]

                # Loop through each broker in the current chunk
                for broker in chunk_brokers:
                    accounts = mappings[broker].get('accounts', [])

                    for account_number in accounts:
                        account_nickname = get_account_nickname(broker, account_number)
                        if should_skip(broker, account_nickname):
                            print(f"Skipping {broker}, {account_nickname} from Should Skip")
                            continue

                    account_count = len(account_mapping[broker])
                    plural_check = "account" if account_count == 1 else "accounts"
                    total_holdings = sum_account_totals(broker)

                    # Add the broker and account information as a field in the embed
                    embed.add_field(
                        name=broker,
                        value=(f"{account_count} {plural_check}\nTotal: ${total_holdings:,.2f}"),
                        inline=True
                    )

                embed.set_footer(text="Try: '..brokerlist <broker>' to list accounts.")
                
                # Send the current embed
                await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"Error loading account mappings: {e}")



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
    mappings = load_account_mappings()
    broker_lower = broker.lower()
    normalized_mappings = {key.lower(): key for key in mappings}

    # Check if the broker exists in the mappings
    if broker_lower not in normalized_mappings:
        available_brokers = ', '.join(mappings.keys())
        await ctx.send(f"Broker {broker} not found. Available brokers: {available_brokers}")
        return
    
    original_broker = normalized_mappings[broker_lower]
    broker_groups = mappings[original_broker]
    total_sum = sum_account_totals(original_broker)

    # Prepare the embed message
    embed = discord.Embed(
        title=f"**{original_broker}**",
        description=f"All active accounts. Total Holdings: ${total_sum:,.2f}",
        color=discord.Color.blue()
    )

    # Iterate over the groups and accounts under each group
    for group_number, accounts in broker_groups.items():
        account_totals = get_account_totals(original_broker, group_number)
        
        for account_number, nickname in accounts.items():
            total = account_totals.get(account_number, 0.0)  # Get total, default to 0 if not found
            embed.add_field(
                name=f"{group_number} - {nickname})",
                value=f"Total: ${total:,.2f}",
                inline=True
            )

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

def sum_account_totals(broker):
    """
    Sum the 'Account Total' for a specific broker from holdings_log.csv.
    
    Parameters:
    - broker: The broker for which to sum account totals.
    
    Returns:
    - The sum of the account totals for the broker.
    """
    # Retrieve the account totals for the broker
    account_totals = get_account_totals(broker)
    
    # Sum all values in the account_totals dictionary

    total_sum = sum(account_totals.values())
    
    return total_sum

def get_account_totals(broker, group_number=None):
    """
    Retrieve the account totals for all accounts under the specified broker and group from holdings_log.csv.
    
    Parameters:
    - broker: The broker for which to get account totals.
    - group_number: The group number to filter accounts (optional).
    
    Returns:
    - A dictionary with account numbers as keys and their total as values.
    """
    account_totals = {}
    with open(HOLDINGS_LOG_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if row['Broker Name'].lower() == broker.lower():
                # Optionally filter by group number if provided
                if group_number and row['Group'] != group_number:
                    continue  # Skip if group number doesn't match
                
                # Add the account number and its total to the dictionary
                account_totals[row['Account']] = float(row['Account Total'])
    
    return account_totals

# -- Helper functions

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


# Update this to broker group no.
def get_account_totals_by_indicator(broker):
    """
    Retrieve and sum account totals for a broker, categorized by the indicator in the nickname (Dre, Lem, or None).
    
    Parameters:
    - broker: The broker for which to get account totals.
    
    Returns:
    - A dictionary with keys 'Dre', 'Lem', and 'None' representing the totals for each category.
    """
    # Initialize totals for each category
    totals = {
        "Dre": 0.0,
        "Lem": 0.0,
        "None": 0.0
    }

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
                if "(Dre)" in nickname:
                    totals["Dre"] += total
                elif "(Lem)" in nickname:
                    totals["Lem"] += total
                else:
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
            totals_by_indicator = get_account_totals_by_indicator(broker)

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

    # This has been capped
    """
    broker_name = broker_name.lower()
    account_number = account_number.lower()

    # Ensure account number is exactly 4 characters long
    if len(account_number) != 4:
        return "Please check that the account number was entered correctly."
        
    # Get brokers, case insensitive    
    mappings = load_account_mappings()
    normalized_mapping = {key.lower(): value for key, value in mappings.items()}

    # Check if the broker exists
    if broker not in mappings:
        return (f"Broker '{broker}' not found. Available brokers: {all_brokers()}")
    
    if should_skip(broker, account_nickname):
        return (f"Skipping {broker} {account_nickname} from Should Skip settings.")
        
    # Check if the broker exists in the normalized mapping
    if broker_name not in normalized_mapping:
        raise ValueError(f"Broker '{broker}' not found. Available brokers: {all_brokers()}")

    # If broker exists, append the account details
    if 'accounts' not in mappings[broker]:
        mappings[broker]['accounts'] = []

    # Check if the account number already exists
    for account in mappings[broker]['accounts']:
        if account['account_number'] == account_number:
            return f"Account '{account_number}' already exists for broker '{broker}'."

    # Add the new account
    new_account = {
        "account_number": account_number,
        "nickname": account_nickname
    }
    mappings[broker]['accounts'].append(new_account)

    # Save the updated mappings
    save_account_mappings(mappings)

    return f"Account '{account_nickname}' for broker '{broker}' added successfully." """
