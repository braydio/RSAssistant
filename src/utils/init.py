# utils/init.py
import logging
import os

from utils.config_utils import (
    get_account_nickname,
    get_today, get_tomorrow,
    load_account_mappings,
    load_config,
    setup_logging,
    CONFIG_PATH
    )

# Load configuration and set up logging
config = load_config()
setup_logging(config)
logging.info("utils.init: Test log message: logging.info")
logging.debug("utils.ini: Test log message: logging.debug")

account_mapping = load_account_mappings()

today = get_today()
tomorrow = get_tomorrow()

# File settings
APP_NAME = config["general_settings"]["app_name"]
FILE_VERSION = config["general_settings"]["file_version"]

# Key file paths
CONFIG_PATH = CONFIG_PATH
DOTENV_PATH = config["paths"]["dotenv"]
TARGET_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
ACCOUNT_MAPPING_FILE = config["paths"]["account_mapping"]
HOLDINGS_LOG_CSV = config["paths"]["holdings_log"]
ORDERS_LOG_CSV = config["paths"]["orders_log"]
ERROR_LOG_FILE = config["paths"]["error_log"]
ERROR_ORDER_DETAILS_FILE = config["paths"]["error_order"]
WATCH_FILE = config["watch_list"]["watch_file"]

EXCEL_FILE_DIRECTORY = config["paths"]["excel_directory"]
EXCEL_FILE_NAME = config["excel_settings"]["excel_file_settings"]["excel_file_name"]
BASE_EXCEL_FILE = config["excel_settings"]["excel_file_settings"]["base_excel_file"]
EXCEL_FILE_MAIN_PATH = os.path.join(
    os.path.normpath(EXCEL_FILE_DIRECTORY), BASE_EXCEL_FILE
)

ORDERS_HEADERS = config["header_settings"]["orders_headers"]
HOLDINGS_HEADERS = config["header_settings"]["holdings_headers"]
EXCLUDED_BROKERS = config.get("excluded_brokers", {})
FILE_ENVIRONMENT = config["environment"]["mode"]

# Misc
