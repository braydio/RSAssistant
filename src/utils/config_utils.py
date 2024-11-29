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

from utils.logging_setup import setup_logging


ENV_PATH = './config/.env'
CONFIG_PATH = 'config/settings.yaml'
CONFIG_INIT = 'config/example-settings.yaml'

# Load configuration dynamically based on the environment
def load_env(env_path=ENV_PATH):
    """
    Load environment variables from a .env file.
    """
    # Resolve the full path
    env_file_path = Path(env_path).resolve()
    if not env_file_path.exists():
        logging.warning(f".env file not found at {env_file_path}")
        return

    load_dotenv(dotenv_path=env_file_path)
    logging.info(f"Loaded in keys from {env_file_path}")

load_env()

def get_full_path(file_path):
    logging.info(f"Resolving file path in config setup : {file_path}")
    runtime = RUNTIME_ENVIRONMENT
    resolved_path = Path(file_path).resolve()

    if not resolved_path.exists():
        logging.warning(f"File not found for {resolved_path}.")
        return
    else:
        # logging.info(f"Resolved file path: {resolved_path}")
        return resolved_path

def load_config(config_path=CONFIG_PATH):
    """
    Loads the YAML config file and returns it as a dictionary.
    Preprocesses paths and validates configuration settings.
    """
    load_env()

    if not os.path.exists(config_path):
        logging.warning(f"Config file not found at {config_path}. Initializing default config.")
        init_missing_file(config_init=CONFIG_INIT, config_path=CONFIG_PATH, description="settings.yaml")

    with open(config_path, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    return config

config = load_config()
VERSION = config["general_settings"]["file_version"]
APP_NAME = config["general_settings"]["app_name"]

def get_file_path(file_path):
    mode = config["environment"]["mode"]
    runtime = 'production'
    if mode.upper() == runtime.upper():
        full_path = get_full_path(file_path)
        logging.info(f"Resolved Full Path : {full_path}")
        return full_path
    else:
        prepend_path = 'dev/' + file_path
        logging.info(f"Dev Environment - Setting dev {prepend_path} for {file_path}")
        full_path = get_full_path(prepend_path)
        logging.info(f"Resolved Dev Path : {full_path}")
        return full_path

def check_runtime():
    production = config["environment"]["mode"]
    check = 'production'
    if production.upper() == check.upper():
        logging.info(f"Production environment detected - Initializing runtime.")
        token = os.getenv("BOT_TOKEN")
        logging.debug("REMOVE TOKEN READ PRINTS AFTER DEBUG")
        logging.info(f"Token = Dev Token = {token}")
        return token
    else:
        logging.info(f"Development environment detected - Initializing dev paths")
        token = os.getenv("DEV_TOKEN")
        logging.debug("REMOVE TOKEN READ PRINTS AFTER DEBUG")
        logging.info(f"Token = Dev Token = {token}")
        return token

BOT_TOKEN = check_runtime()
DISCORD_PRIMARY_CHANNEL = os.getenv("DISCORD_CHANNEL_ID")
DISCORD_SECONDARY_CHANNEL = os.getenv("DISCORD_CHANNEL_ID2")

def init_missing_file(src_path, dest_path, description="file"):
    """
    Copy src_path to dest_path if dest_path does not exist.
    
    Args:
        src_path (str): Path to the source file (template or example file).
        dest_path (str): Path to the destination where the file should exist.
        description (str): Description of the file being initialized, e.g., "config file".
    """
    try:
        # Check if destination file already exists
        if not os.path.exists(dest_path):
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # Copy the source file to the destination
            shutil.copyfile(src_path, dest_path)
            logging.info(f"Initialized new {description} from template: {src_path} -> {dest_path}")
        else:
            logging.info(f"{description.capitalize()} already exists at: {dest_path}")
    except Exception as e:
        logging.error(f"Failed to initialize {description} from {src_path}: {str(e)}")
        raise

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

# Initialize logging
setup_logging(config)

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
