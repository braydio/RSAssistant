import asyncio
import csv
import json
import logging
import os
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from colorama import Fore, Style, init

import discord
import yaml
import yfinance as yf
from dotenv import load_dotenv


# Load configuration dynamically based on the environment
env = os.getenv("ENVIRONMENT", "production").lower()
logging.debug(f"Environment variable loaded: {env}")
if env not in ['prduction', 'development']:
    logging.warning(f"Unrecognized environment '{env}', defaulting to 'production'.")
    env = 'production'
instance = "src" if env == "production" else "dev"


BASE_DIR = Path(__file__).resolve().parent.parent.parent
logging.info(BASE_DIR)
CONFIG_DIR = BASE_DIR / "config"
CONFIG_PATH = CONFIG_DIR / "settings.yaml"  # Central template config
CONFIG_INIT = CONFIG_DIR / "example-settings.yaml"
BASE_ENV = CONFIG_DIR / ".env"

CONFIG_FILES = {
    "production": {
        "config_file": BASE_DIR / "src" / "config" / "settings.yaml",
        "dotenv_file": BASE_DIR / "src" / "config" / ".env",
        "account_mapping_file": BASE_DIR / "src" / "config" / "account_mapping.json",
        "base_prefix": "src"
    },
    "development": {
        "config_file": BASE_DIR / "dev" / "config" / "settings.yaml",
        "dotenv_file": BASE_DIR / "dev" / "config" / ".env",
        "account_mapping_file": BASE_DIR / "dev" / "config" / "account_mapping.json",
        "base_prefix": "dev"
    }
}

CONFIG_FILE = CONFIG_FILES[env]["config_file"]
DOTENV_FILE = CONFIG_FILES[env]["dotenv_file"]
ACCOUNT_MAPPING_FILE = CONFIG_FILES[env]["account_mapping_file"]

load_dotenv(DOTENV_FILE)

def parse_size(size_str):
    """Parse a human-readable size string (e.g., '10MB') and return its size in bytes."""
    size_str = str(size_str).strip().upper()
    if size_str.endswith("KB"):
        return int(size_str[:-2]) * 1024
    elif size_str.endswith("MB"):
        return int(size_str[:-2]) * 1024 * 1024
    elif size_str.endswith("GB"):
        return int(size_str[:-2]) * 1024 * 1024 * 1024
    else:
        return int(size_str)  # Assume it's already in bytes if no suffix

def setup_logging(config=None, verbose=False):
    """Set up logging based on the given configuration."""
    # Use default logging values if config is not yet loaded
    log_level = (
        "DEBUG"
        if verbose
        else (
            config.get("logging", {}).get("level", "INFO").upper() if config else "INFO"
        )
    )
    log_file = (
        config.get("logging", {}).get("file", "logs/app.log")
        if config
        else "volumes/logs/app.log"
    )
    max_size = (
        int(config.get("logging", {}).get("max_size", 10485760)) if config else 10485760
    )
    backup_count = config.get("logging", {}).get("backup_count", 2) if config else 2

    # Ensure the logs directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Clear existing handlers to avoid duplicate logs
    logging.getLogger().handlers.clear()

    # Set up file handler
    handler = RotatingFileHandler(log_file, maxBytes=max_size, backupCount=backup_count)
    handler.setLevel(getattr(logging, log_level, logging.INFO))

    # Set up console handler with UTF-8 encoding
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    console_handler.stream = open(1, "w", encoding="utf-8", closefd=False)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[handler, console_handler],
    )

    # Suppress third-party logs
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)

    # Add deduplication filter
    class TimeLengthListDuplicateFilter(logging.Filter):
        def __init__(self, interval=60, max_message_length=200, max_sample_items=5):
            super().__init__()
            self.logged_messages = {}
            self.interval = interval  # Minimum interval (in seconds) to allow duplicate messages
            self.max_message_length = max_message_length
            self.max_sample_items = max_sample_items

        def log_sample(self, data, label="Sample"):
            """Logs a sample of the data."""
            if isinstance(data, (list, tuple)):
                sample_data = data[:self.max_sample_items]
                logging.info(f"{label} (showing up to {self.max_sample_items} items): {sample_data}...")
            elif isinstance(data, dict):
                sample_data = {k: data[k] for k in list(data.keys())[:self.max_sample_items]}
                logging.info(f"{label} (showing up to {self.max_sample_items} key-value pairs): {sample_data}...")
            else:
                logging.info(f"{label}: {str(data)}")

        def truncate_message(self, msg):
            """Truncates a message if it exceeds a specified length."""
            msg_str = str(msg)
            return msg_str if len(msg_str) <= self.max_message_length else f"{msg_str[:self.max_message_length]}... [truncated]"

        def filter(self, record):
            current_time = time.time()

            # Handle unhashable messages
            try:
                msg_key = hash(record.msg)
            except TypeError:  # Handle unhashable messages like lists or dicts
                if isinstance(record.msg, (list, dict)):
                    self.log_sample(record.msg, label="Unhashable message logged")
                    return False  # Skip logging the original message
                msg_key = id(record.msg)

            # Deduplication check
            if msg_key in self.logged_messages:
                last_logged_time = self.logged_messages[msg_key]
                if current_time - last_logged_time < self.interval:
                    return False

            # Truncate long messages
            record.msg = self.truncate_message(record.msg)
            self.logged_messages[msg_key] = current_time
            return True


    logging.getLogger().addFilter(TimeLengthListDuplicateFilter())

    # Add colorized formatting for console logs
    class ColorFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG: Fore.BLUE,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT,
        }

        def format(self, record):
            log_color = self.COLORS.get(record.levelno, "")
            record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
            return super().format(record)

    console_handler.setFormatter(ColorFormatter("%(asctime)s - %(levelname)s - %(message)s"))


    # Add utility methods for sampling and truncation
    def log_sample(data, max_items=5, label="Sample"):
        """
        Logs a sample of the data to avoid overwhelming the log with large datasets.
        """
        if isinstance(data, (list, tuple)):
            sample_data = data[:max_items]
            logging.info(f"{label} (showing up to {max_items} items): {sample_data}...")
        elif isinstance(data, dict):
            sample_data = {k: data[k] for k in list(data.keys())[:max_items]}
            logging.info(f"{label} (showing up to {max_items} key-value pairs): {sample_data}...")
        else:
            logging.info(f"{label}: {str(data)}")

    def truncate_message(msg, max_length=200):
        """
        Truncates a log message if it exceeds a specified length.
        """
        msg_str = str(msg)
        return msg_str if len(msg_str) <= max_length else f"{msg_str[:max_length]}... [truncated]"
    

    # Attach the helpers to the logger object
    logging.log_sample = log_sample
    logging.truncate_message = truncate_message

    logging.info("Logging setup complete.")

# Initialize logging before any other operations
setup_logging()
# Sync configuration files
def sync_config(env):
    """
    Sync the environment-specific configuration file with the central template.
    """
    target_path = CONFIG_FILES[env]["config_file"]
    # Load the template DE
    with open(CONFIG_PATH, "r", encoding="utf-8") as template_file:
        template_config = yaml.safe_load(template_file)

    # Initialize the target config if it doesn't exist
    if not target_path.exists():
        logging.info(f"{target_path} does not exist. Initializing from template.")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONFIG_PATH, target_path)
        return template_config

    # Load the target configuration
    with open(target_path, "r", encoding="utf-8") as target_file:
        target_config = yaml.safe_load(target_file)

    # Sync missing keys
    updated = False
    for key, value in template_config.items():
        if key not in target_config:
            target_config[key] = value
            updated = True

    # Save the updated configuration
    if updated:
        with open(target_path, "w", encoding="utf-8") as target_file:
            yaml.dump(target_config, target_file)
            logging.info(f"Updated {target_path} with missing keys from template.")

    # Adjust paths in the configuration based on the environment
    paths = target_config.get("paths", {})
    base_prefix = CONFIG_FILES[env]["base_prefix"]

    for key, raw_path in paths.items():
        raw_path = Path(raw_path)  # Convert to Path object for safer manipulation
        if raw_path.parts[0] == "volumes":
            # If path starts with 'volumes/' handle based on environment
            if env == "development":
                # Development: Prepend 'dev/' to 'volumes/'
                paths[key] = str(Path("dev") / raw_path)
            else:
                # Production: Leave 'volumes/' paths unchanged
                paths[key] = str(raw_path)
        else:
            # For all other paths, prepend 'base_prefix' based on environment
            paths[key] = str(Path(base_prefix) / raw_path)

    target_config["paths"] = paths
    return target_config

def validate_config(config):
    """Ensure the configuration has all required sections and paths."""
    required_sections = ["paths", "general_settings", "discord", "environment"]
    required_paths = ["holdings_log", "manual_orders", "account_mapping"]

    missing_sections = [section for section in required_sections if section not in config]
    if missing_sections:
        logging.error(f"Missing required config sections: {missing_sections}")
        raise KeyError(f"Config missing sections: {missing_sections}")

    missing_paths = [path for path in required_paths if path not in config.get("paths", {})]
    if missing_paths:
        logging.error(f"Missing required paths in config: {missing_paths}")
        raise KeyError(f"Config paths missing keys: {missing_paths}")

    logging.info("Configuration validated successfully.")

# Load configuration
def load_config():
    """Load, preprocess, and validate configuration."""
    env = os.getenv("ENVIRONMENT", "production").lower()
    config = sync_config(env)

    validate_config(config)

    config["discord"]["token"] = os.getenv("BOT_TOKEN", config["discord"].get("token"))
    config["discord"]["channel_id"] = os.getenv("DISCORD_CHANNEL_ID", config["discord_ids"].get("channel_id"))

    return config

config = load_config()
setup_logging(config)

# Save configuration
def save_config(config, path=CONFIG_PATH):
    """Save configuration to the specified path."""
    os.makedirs(path.parent, exist_ok=True)
    print(path, config)
    with open(path, "w", encoding="utf-8") as temp_config:
        yaml.dump(config, temp_config)


# Load the configuration (make sure the config is loaded before accessing its keys)
RUNTIME_ENVIRONMENT = config["environment"]["mode"]
HOLDINGS_LOG_CSV = config["paths"]["holdings_log"]
ORDERS_LOG_CSV = config["paths"]["orders_log"]
MANUAL_ORDER_ENTRY_TXT = config["paths"]["manual_orders"]
ACCOUNT_MAPPING_FILE = config["paths"]["account_mapping"]
EXCLUDED_BROKERS = config.get("excluded_brokers", {})
ACCOUNT_OWNERS = config.get("account_owners", {})

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


# -- Misc utility functions


def get_today():
    """Return today's date in MM-DD format."""
    return datetime.now().strftime("%m-%d")


def get_tomorrow():
    """Return tomorrow's date in MM-DD format."""
    return (datetime.now() + timedelta(days=1)).strftime("%m-%d")
