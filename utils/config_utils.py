import os
import logging
import yaml
import json
from pathlib import Path
import dotenv
from utils.logging_setup import setup_logging

# Paths
ENV_PATH = 'config/.env'
DEFAULT_CONFIG_PATH = 'config/settings.yaml'

# Cache for loaded configuration
_config_cache = None

# Dynamically resolve base directory (inside Docker or outside)
def get_base_dir():
    logging.debug("Determining the base directory...")
    if os.path.exists('/.dockerenv') or os.path.isfile('/proc/1/cgroup'):
        logging.info("Running inside Docker container, setting base directory to /app")
        return Path("/app")  # Base directory inside Docker
    else:
        logging.info("Running outside Docker container, setting base directory to script's location")
        return Path(__file__).parent  # Base directory outside Docker

def resolve_path(relative_path, create_if_missing=False):
    """
    Resolve a file path relative to the script's directory or base directory,
    dynamically handling whether the script is running inside Docker or not.
    """
    logging.debug(f"Resolving path for: {relative_path}")
    base_dir = get_base_dir()

    # If the relative path is already absolute, resolve it directly
    if not Path(relative_path).is_absolute():
        resolved = Path(base_dir, relative_path).resolve()
        logging.debug(f"Resolved relative path: {resolved}")
    else:
        resolved = Path(relative_path).resolve()
        logging.debug(f"Resolved absolute path: {resolved}")

    if create_if_missing and not resolved.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.touch()  # Create the file
        logging.info(f"Created missing path: {resolved}")
    
    return resolved

def load_env(env_path=ENV_PATH):
    """
    Load environment variables from a .env file.
    """
    logging.debug(f"Loading environment variables from {env_path}")
    env_file = resolve_path(env_path)  # Resolve relative .env path
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_file)
        logging.info(f"Environment variables loaded from {env_file}")
    else:
        logging.warning(f".env file not found at {env_file}")

load_env()

def initialize_config(config_path=DEFAULT_CONFIG_PATH):
    """
    Ensure the configuration file exists.
    """
    logging.debug(f"Initializing configuration from {config_path}")
    config_file = resolve_path(config_path)  # Resolve the configuration file path
    if not config_file.exists():
        logging.error(f"Config file is missing: {config_file}")
        raise FileNotFoundError(f"Config file is missing: {config_file}")
    logging.info(f"Config file found: {config_file}")
    return config_file

def load_config(config_path=DEFAULT_CONFIG_PATH):
    """
    Load the YAML configuration file once and cache it.
    """
    global _config_cache
    if _config_cache is not None:
        logging.debug("Returning cached configuration")
        return _config_cache

    logging.debug(f"Loading configuration from {config_path}")
    config_file = initialize_config(config_path)
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            _config_cache = yaml.safe_load(f)
            logging.info(f"Configuration loaded from {config_file}")
            return _config_cache
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML config: {e}")
        raise

# Paths
ENV_PATH = 'config/.env'
DEFAULT_CONFIG_PATH = 'config/settings.yaml'

# Cache for loaded configuration
_config_cache = None

# Resolved Paths
DISCORD_PRIMARY_CHANNEL = None
DISCORD_PRIMARY_CHANNEL = None
ACCOUNT_MAPPING_FILE = None
EXCEL_FILE_MAIN = None
HOLDINGS_LOG_CSV = None
ORDERS_LOG_CSV = None
SQL_DATABASE_DB = None
WATCH_FILE = None
VERSION = None


# Logging the environment variable loading
DISCORD_TOKEN = os.getenv("BOT_TOKEN")
logging.info(f"Loaded BOT_TOKEN: {DISCORD_TOKEN}")

# Pre-resolve paths for shared use
logging.debug("Loading configuration and resolving paths...")
config = load_config()
DISCORD_PRIMARY_CHANNEL = int(os.getenv("DISCORD_PRIMARY_CHANNEL"))
DISCORD_SECONDARY_CHANNEL = int(os.getenv("DISCORD_SECONDARY_CHANNEL"))

# Resolve all the file paths and log them
ACCOUNT_MAPPING_FILE = resolve_path("config/account_mapping.json",create_if_missing=True)
EXCEL_FILE_MAIN = resolve_path("volumes/excel/ReverseSplitLog.xlsx",create_if_missing=True)
HOLDINGS_LOG_CSV = resolve_path("volumes/logs/holdings_log.csv",create_if_missing=True)
ORDERS_LOG_CSV = resolve_path("volumes/logs/orders_log.csv",create_if_missing=True)
SQL_DATABASE_DB = resolve_path("volumes/db/reverse_splits.db", create_if_missing=True)
ERROR_LOG_FILE = resolve_path("volumes/logs/error_log.txt", create_if_missing=True)
WATCH_FILE = resolve_path("config/watch_list.json",create_if_missing=True)
VERSION = ("app_version", "0.0.0")

logging.info(f"Resolved EXCEL_FILE_MAIN_PATH: {EXCEL_FILE_MAIN}")
logging.info(f"Resolved HOLDINGS_LOG_CSV: {HOLDINGS_LOG_CSV}")
logging.info(f"Resolved ORDERS_LOG_CSV: {ORDERS_LOG_CSV}")
logging.info(f"Resolved DATABASE_FILE: {SQL_DATABASE_DB}")
logging.info(f"Resolved ERROR_LOG: {ERROR_LOG_FILE}")
logging.info(f"Resolved WATCH_FILE: {WATCH_FILE}")

def load_account_mappings(file=ACCOUNT_MAPPING_FILE):
    """Loads account mappings from the JSON file and ensures the data structure is valid."""
    logging.debug(f"Loading account mappings from {file}")
    if not os.path.exists(file):
        logging.error(f"Account mapping file {file} not found.")
        return {}

    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            logging.debug(f"Account mapping data loaded successfully.")
            if not isinstance(data, dict):
                logging.error(f"Invalid account mapping structure in {file}. Expected a dictionary.")
                return {}

            for broker, broker_data in data.items():
                if not isinstance(broker_data, dict):
                    logging.error(f"Invalid data for broker '{broker}'. Expected a dictionary.")
                    continue

                for group, accounts in broker_data.items():
                    if not isinstance(accounts, dict):
                        logging.error(f"Invalid group structure for '{group}' in broker '{broker}'. Expected a dictionary.")
                        broker_data[group] = {}

            return data

    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {file}: {e}")
        return {}

def save_account_mappings(mappings):
    """Save the account mappings to the JSON file."""
    logging.debug(f"Saving account mappings to {ACCOUNT_MAPPING_FILE}")
    with open(ACCOUNT_MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=4)
    logging.info(f"Account mappings saved to {ACCOUNT_MAPPING_FILE}")

def get_account_nickname(broker, group_number, account_number):
    """
    Retrieves the account nickname from the account mapping,
    or returns the account number if the mapping is not found.
    """
    logging.debug(f"Retrieving nickname for broker: {broker}, group: {group_number}, account: {account_number}")
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)

    account_number_str = str(account_number)
    group_number_str = str(group_number)
    broker_accounts = account_mapping.get(broker, {})

    if not broker_accounts:
        logging.warning(f"No account mappings found for broker: {broker}. Using account number as fallback.")
        return account_number_str

    group_accounts = broker_accounts.get(group_number_str, {})
    nickname = group_accounts.get(account_number_str, account_number_str)
    logging.info(f"Retrieved nickname: {nickname}")
    return nickname


ACCOUNT_MAPPING = load_account_mappings(file=ACCOUNT_MAPPING_FILE)
logging.info(f"Resolved ACCOUNT_MAPPING_FILE: {ACCOUNT_MAPPING_FILE}")



ENABLE_CSV_LOGGING = config.get("general_settings", {}).get("enable_csv_logging", False)
ENABLE_EXCEL_LOGGING = config.get("general_settings", {}).get("enable_excel_logging", False)
ENABLE_SQL_LOGGING = config.get("general_settings", {}).get("enable_sql_logging", False)

def csv_toggle(func):
    """
    Decorator to ensure CSV logging is enabled before executing the function.
    """
    def wrapper(*args, **kwargs):
        if not ENABLE_CSV_LOGGING:
            logging.warning(f"CSV logging is disabled. Skipping {func.__name__}.")
            logging.error(f"Most core functionality of this script relies on CSV logging. Please enable it in the configuration.")
            logging.info(f"Check the settings.yaml at {DEFAULT_CONFIG_PATH}")
            return None  # Skip execution
        return func(*args, **kwargs)
    return wrapper

def excel_toggle(func):
    def wrapper(*args, **kwargs):
        if not ENABLE_EXCEL_LOGGING:
            logging.warning(f"Excel logging is disabled. Skipping {func.__name__}.")
            return None
        return func(*args, **kwargs)
    return wrapper

def sql_toggle(func):
    def wrapper(*args, **kwargs):
        if not ENABLE_SQL_LOGGING:
            logging.warning(f"SQL logging is disabled. Skipping {func.__name__}.")
            return None
        return func(*args, **kwargs)
    return wrapper

