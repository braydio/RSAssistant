import os
import logging
import yaml
import json
from pathlib import Path
import dotenv

# Paths
ENV_PATH = './config/.env'
DEFAULT_CONFIG_PATH = './config/settings.yaml'

# Cache for loaded configuration
_config_cache = None

# Resolved Paths
ACCOUNT_MAPPING_FILE = None
EXCEL_FILE_ACTIVE = None
HOLDINGS_LOG_CSV = None
ORDERS_LOG_CSV = None
SQL_DATABASE_DB = None


def setup_logging():
    """
    Set up basic logging configuration.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),  # Log to console
            logging.FileHandler("application.log")  # Log to a file
        ]
    )

def load_env(env_path=ENV_PATH):
    """
    Load environment variables from a .env file.
    """
    env_file = Path(env_path).resolve()
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_file)
        logging.info(f"Environment variables loaded from {env_file}")
    else:
        logging.warning(f".env file not found at {env_file}")

def initialize_config(config_path=DEFAULT_CONFIG_PATH):
    """
    Ensure the configuration file exists.
    """
    config_file = Path(config_path).resolve()

    if not config_file.exists():
        raise FileNotFoundError(f"Config file is missing: {config_file}")

    return config_file

def load_config(config_path=DEFAULT_CONFIG_PATH):
    """
    Load the YAML configuration file once and cache it.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_file = initialize_config(config_path)
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            _config_cache = yaml.safe_load(f)
            logging.info(f"Configuration loaded from {config_file}")
            return _config_cache
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML config: {e}")
        raise

def resolve_path(relative_path, create_if_missing=False):
    """
    Resolve a file path relative to the script's directory or base directory.
    """
    base_dir = Path(__file__).parent
    resolved = Path(base_dir, relative_path).resolve()

    if create_if_missing and not resolved.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.touch()  # Create the file
        logging.info(f"Created missing path: {resolved}")
    return resolved

def get_setting(key, default=None):
    """
    Retrieve a setting from the loaded configuration.
    """
    config = load_config()
    value = config
    try:
        for part in key.split("."):
            value = value[part]
        return value
    except KeyError:
        logging.warning(f"Setting not found: {key}. Using default: {default}")
        return default

# Pre-resolve paths for shared use
config = load_config()
ACCOUNT_MAPPING_FILE = resolve_path(get_setting("paths.account_mapping"), create_if_missing=True)
EXCEL_FILE_ACTIVE = resolve_path(get_setting("paths.excel_main"), create_if_missing=True)
HOLDINGS_LOG_CSV = resolve_path(get_setting("paths.holdings_log"), create_if_missing=True)
ORDERS_LOG_CSV = resolve_path(get_setting("paths.orders_log"), create_if_missing=True)
SQL_DATABASE_DB = resolve_path(get_setting("paths.database", "db/reverse_splits.db"), create_if_missing=True)

logging.info(f"Resolved ACCOUNT_MAPPING_FILE: {ACCOUNT_MAPPING_FILE}")
logging.info(f"Resolved EXCEL_FILE_MAIN_PATH: {EXCEL_FILE_ACTIVE}")
logging.info(f"Resolved HOLDINGS_LOG_CSV: {HOLDINGS_LOG_CSV}")
logging.info(f"Resolved ORDERS_LOG_CSV: {ORDERS_LOG_CSV}")
logging.info(f"Resolved DATABASE_FILE: {SQL_DATABASE_DB}")

# Account Mapping / Nicknames

def load_account_mappings():
    """Loads account mappings from the JSON file and ensures the data structure is valid."""
    if not os.path.exists(ACCOUNT_MAPPING_FILE):
        logging.error(f"Account mapping file {ACCOUNT_MAPPING_FILE} not found.")
        return {}

    try:
        with open(ACCOUNT_MAPPING_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

            if not isinstance(data, dict):
                logging.error(
                    f"Invalid account mapping structure in {ACCOUNT_MAPPING_FILE}."
                )
                return {}

            for broker, broker_data in data.items():
                if not isinstance(broker_data, dict):
                    logging.error(f"Invalid data for broker '{broker}'.")
                    continue

                for group, accounts in broker_data.items():
                    if not isinstance(accounts, dict):
                        logging.error(
                            f"Invalid group structure for '{group}' in broker '{broker}'."
                        )
                        broker_data[group] = {}

            return data

    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {ACCOUNT_MAPPING_FILE}: {e}")
        return {}


def save_account_mappings(mappings):
    """Save the account mappings to the JSON file."""
    with open(ACCOUNT_MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=4)


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
