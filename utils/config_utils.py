import yaml
import os
import json
import logging
import discord

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

def get_account_nickname(broker, account_number):
    """
    Retrieves the account nickname from the account mapping,
    or returns the account number if the mapping is not found.
    """
    account_mapping = load_account_mappings()

    if not account_mapping:
        logging.error("Account mappings are empty or not loaded.")
        return account_number

    broker_accounts = account_mapping.get(broker, {})

    if not broker_accounts:
        logging.warning(f"No account mappings found for broker: {broker}. Returning account number.")
        return account_number

    return broker_accounts.get(account_number, account_number)

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
    
def save_account_mappings(mappings):
    """Save the account mappings to the JSON file."""
    with open(ACCOUNT_MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=4)

def add_account(broker, account_number, account_nickname):
    """
    Add an account to a broker.
    
    Parameters:
    - broker: The broker to which the account belongs.
    - account_number: The 4-character account number.
    - account_nickname: A nickname for the account.
    
    Returns:
    - A success or error message.
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

    return f"Account '{account_nickname}' for broker '{broker}' added successfully."

async def all_brokers(ctx, filename=ACCOUNT_MAPPING_FILE):
    """
    Returns a list of active brokers based on the account mapping file.
    """
    with open(filename, 'r') as f:
        account_mapping = json.load(f)

        active_brokers = list(account_mapping.keys())

        embed = discord.Embed(
            title="**All Active Brokers**",
            description="",
            color=discord.Color.blue()
        )

        # Loop through active brokers and add them as fields in the embed
        for broker in active_brokers:
            account_count = len(account_mapping[broker])
            if account_count == 1:
                plural_check = "account"
            else:
                plural_check = "accounts"

            embed.add_field(
                name=broker,
                value=(f"{account_count} {plural_check}"),
                inline=True
            )

        footer = f"'..brokerwith <*broker*>' "

        embed.set_footer(text="Try: '..brokerlist <broker>' to list accounts.")

        await ctx.send(embed=embed)

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
    Retrieve all account nicknames for a given broker.
    
    Parameters:
    - broker: The broker for which to retrieve account nicknames.
    
    Returns:
    - A list of nicknames or an error message if the broker is not found.
    """
    mappings = load_account_mappings()
    normalized_mappings = {key.lower(): key for key in mappings}

    broker_lower = broker.lower()

    # Check if the broker exists
    if broker_lower not in normalized_mappings:
        available_brokers = ', '.join(mappings.keys())
        await ctx.send(f"Broker {broker} not found. Available brokers:{available_brokers} | {all_brokers()}")
        return
    
    original_broker = normalized_mappings[broker_lower]

    accounts = mappings[original_broker]
    nicknames = accounts.values()

    # Prepare the embed message
    embed = discord.Embed(
        title=f"**{original_broker}**",
        description="All active accounts:",
        color=discord.Color.blue()
    )

    # Add each account nickname to the embed
    for nickname in nicknames:
        embed.add_field(
            name=nickname,
            value="This will display the total value.",
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
