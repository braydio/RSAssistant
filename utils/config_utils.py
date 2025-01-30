import json
import logging
import os
from pathlib import Path

import dotenv
import yaml

from utils.logging_setup import setup_logging

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent  # Move up one directory from utils
CONFIG_DIR = BASE_DIR / "config"
VOLUMES_DIR = BASE_DIR / "volumes"

# Paths
ENV_PATH = CONFIG_DIR / ".env"
CONFIG_FILE = CONFIG_DIR / "settings.yaml"
ACCOUNT_MAPPING = CONFIG_DIR / "account_mapping.json"
WATCH_FILE = CONFIG_DIR / "watch_list.json"
SELL_FILE = CONFIG_DIR / "sell_list.json"
EXCEL_FILE_MAIN = VOLUMES_DIR / "excel" / "ReverseSplitLog.xlsx"
HOLDINGS_LOG_CSV = VOLUMES_DIR / "logs" / "holdings_log.csv"
ORDERS_LOG_CSV = VOLUMES_DIR / "logs" / "orders_log.csv"
SQL_DATABASE = VOLUMES_DIR / "db" / "reverse_splits.db"
ERROR_LOG_FILE = VOLUMES_DIR / "logs" / "error_log.txt"


# Cache for loaded configuration
_config_cache = None


def load_env():
    """
    Load environment variables from a .env file.
    """
    if ENV_PATH.exists():
        dotenv.load_dotenv(dotenv_path=ENV_PATH)
        logging.info(f"Environment variables loaded from {ENV_PATH}")
    else:
        logging.warning(f".env file not found at {ENV_PATH}")


def load_config():
    """
    Load the YAML configuration file once and cache it.
    """
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    if not CONFIG_FILE.exists():
        logging.error(f"Config file is missing: {CONFIG_FILE}")
        raise FileNotFoundError(f"Config file is missing: {CONFIG_FILE}")

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            _config_cache = yaml.safe_load(f)
            logging.info(f"Configuration loaded from {CONFIG_FILE}")
            return _config_cache
    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML config: {e}")
        raise

load_env()
config = load_config()
VERSION = config.get("app_version", "development 0.1")

# Resolved Paths
DISCORD_PRIMARY_CHANNEL = int(os.getenv("DISCORD_PRIMARY_CHANNEL", 0))
DISCORD_SECONDARY_CHANNEL = int(os.getenv("DISCORD_SECONDARY_CHANNEL", 0))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
logging.info(f"Loaded BOT_TOKEN: {BOT_TOKEN}")

logging.info(f"Resolved EXCEL_FILE_MAIN_PATH: {EXCEL_FILE_MAIN}")
logging.info(f"Resolved HOLDINGS_LOG_CSV: {HOLDINGS_LOG_CSV}")
logging.info(f"Resolved ORDERS_LOG_CSV: {ORDERS_LOG_CSV}")
logging.info(f"Resolved DATABASE_FILE: {SQL_DATABASE}")
logging.info(f"Resolved ERROR_LOG: {ERROR_LOG_FILE}")
logging.info(f"Resolved WATCH_FILE: {WATCH_FILE}")
logging.info(f"Resolved SELLING_FILE: {SELL_FILE}")


def load_account_mappings():
    """Loads account mappings from the JSON file and ensures the data structure is valid."""
    logging.debug(f"Loading account mappings from {ACCOUNT_MAPPING}")
    if not ACCOUNT_MAPPING.exists():
        logging.error(f"Account mapping file {ACCOUNT_MAPPING} not found.")
        return {}

    try:
        with open(ACCOUNT_MAPPING, "r", encoding="utf-8") as f:
            data = json.load(f)
            logging.debug(f"Account mapping data loaded successfully.")
            if not isinstance(data, dict):
                logging.error(f"Invalid account mapping structure in {ACCOUNT_MAPPING}. Expected a dictionary.")
                return {}
            return data
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON from {ACCOUNT_MAPPING}: {e}")
        return {}


def save_account_mappings(mappings):
    """Save the account mappings to the JSON file."""
    logging.debug(f"Saving account mappings to {ACCOUNT_MAPPING}")
    with open(ACCOUNT_MAPPING, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=4)
    logging.info(f"Account mappings saved to {ACCOUNT_MAPPING}")

def get_broker_name(broker_number):
    """Retrieve the broker name based on broker number."""
    mappings = load_account_mappings()
    for broker, accounts in mappings.items():
        if str(broker_number) in accounts:
            return broker
    return None


def get_broker_group(broker_name):
    """Retrieve all broker numbers associated with a given broker name."""
    mappings = load_account_mappings()
    return list(mappings.get(broker_name, {}).keys())


def get_account_number(broker_name, broker_number):
    """Retrieve all account numbers under a given broker and broker number."""
    mappings = load_account_mappings()
    return list(mappings.get(broker_name, {}).get(str(broker_number), {}).keys())


def get_account_nickname(broker_name, broker_number, account_number):
    """Retrieve the nickname associated with a given broker, broker number, and account number."""
    mappings = load_account_mappings()
    return mappings.get(broker_name, {}).get(str(broker_number), {}).get(account_number, None)

# Logging setup
setup_logging(config=config)
