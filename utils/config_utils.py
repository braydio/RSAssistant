import yaml
import os
import json
import logging

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

def all_brokers(filename=ACCOUNT_MAPPING_FILE):
    """
    Returns a list of active brokers based on the account mapping file.
    """
    try:
        # Load the account mappings from the file
        with open(filename, 'r') as f:
            account_mapping = json.load(f)
        
        # Get the list of active brokers (keys of the account_mapping dictionary)
        active_brokers = list(account_mapping.keys())
        
        return active_brokers
    except FileNotFoundError:
        print(f"Error: The file {filename} was not found.")
        return []
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from {filename}.")
        return []