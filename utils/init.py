import os
import logging
import pathlib
from utils.config_utils import (
    setup_logging,
    load_config,
    load_env,
    load_account_mappings,
    save_account_mappings,
    get_account_nickname,
    get_today,
    get_tomorrow,
    get_file_path,
    CONFIG_PATH,
    RUNTIME_ENVIRONMENT,
    HOLDINGS_LOG_CSV,
    ORDERS_LOG_CSV,
    MANUAL_ORDER_ENTRY_TXT,
    ACCOUNT_MAPPING_FILE,
    EXCLUDED_BROKERS,
    ACCOUNT_OWNERS,
    BOT_TOKEN,
    DISCORD_PRIMARY_CHANNEL,
    DISCORD_SECONDARY_CHANNEL
)

# Load configuration and set up logging
config = load_config()

setup_logging(config)
logging.info("utils.init: Test log message: logging.info")
logging.debug("utils.ini: Test log message: logging.debug")

# Use imported functions and variables
account_mapping = load_account_mappings()
today = get_today()
tomorrow = get_tomorrow()

# File settings
APP_NAME = config["general_settings"]["app_name"]
FILE_VERSION = config["general_settings"]["file_version"]


# Key file paths
TARGET_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
ALERTS_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID2")
ERROR_LOG_FILE = config["paths"]["error_log"]
ERROR_ORDER_DETAILS_FILE = config["paths"]["error_order"]
WATCH_FILE = config["watch_list"]["watch_file"]

EXCEL_FILE_DIRECTORY = config["paths"]["excel_directory"]
EXCEL_FILE_NAME = config["paths"]["excel_file_name"]
BASE_EXCEL_FILE = config["paths"]["base_excel_file"]
EXCEL_FILE_MAIN_PATH = os.path.join(
    os.path.normpath(EXCEL_FILE_DIRECTORY), BASE_EXCEL_FILE
)

CONFIG_PATH = get_file_path(CONFIG_PATH)
WATCH_FILE = get_file_path(WATCH_FILE)
ACCOUNT_MAPPING_FILE = get_file_path(ACCOUNT_MAPPING_FILE)
EXCEL_FILE_MAIN_PATH = get_file_path(EXCEL_FILE_MAIN_PATH)
ORDERS_LOG_CSV = get_file_path(ORDERS_LOG_CSV)
HOLDINGS_LOG_CSV = get_file_path(HOLDINGS_LOG_CSV)

ORDERS_HEADERS = config["header_settings"]["orders_headers"]
HOLDINGS_HEADERS = config["header_settings"]["holdings_headers"]
RUNTIME_ENVIRONMENT = config["environment"]["mode"]


# Use imported functions and variables
account_mapping = load_account_mappings()
today = get_today()
tomorrow = get_tomorrow()

logging.info(f"Configuration loaded: {CONFIG_PATH}")
logging.info(f"Watchlist from: {WATCH_FILE}")
logging.info(f"Excel log loaded at {EXCEL_FILE_MAIN_PATH}")
logging.info(f"Account mapped from mapping file at: {ACCOUNT_MAPPING_FILE}")



# Export relevant values for other modules
__all__ = [
    "setup_logging",
    "load_config",
    "load_account_mappings",
    "save_account_mappings",
    "get_account_nickname",
    "today",
    "tomorrow",
    "CONFIG_PATH",
    "RUNTIME_ENVIRONMENT",
    "HOLDINGS_LOG_CSV",
    "ORDERS_LOG_CSV",
    "MANUAL_ORDER_ENTRY_TXT",
    "ACCOUNT_MAPPING_FILE",
    "EXCLUDED_BROKERS",
    "ACCOUNT_OWNERS",
    "config"
    "BOT_TOKEN",
    "DISCORD_PRIMARY_CHANNEL",
    "DISCORD_SECONDARY_CHANNEL"
]
