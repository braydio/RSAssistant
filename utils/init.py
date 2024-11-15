
# utils/init.py
import os
import logging

from utils.config_utils import (
    load_config,
    setup_logging,
    get_account_nickname,
    load_account_mappings,
    get_last_stock_price,
    send_large_message_chunks,
    get_today,
    get_tomorrow
)

# Load configuration and set up logging
config = load_config()
setup_logging(config)
logging.info("utils.init: Test log message: logging.info")
logging.debug("utils.ini: Test log message: logging.debug")

account_mapping = load_account_mappings()

today = get_today()
tomorrow = get_tomorrow()

# Key file paths
TARGET_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']
ERROR_LOG_FILE = config['paths']['error_log']
ERROR_ORDER_DETAILS_FILE = config['paths']['error_order']

EXCEL_FILE_DIRECTORY = config['paths']['excel_directory']
EXCEL_FILE_NAME = config['paths']['excel_file_name']
BASE_EXCEL_FILE = config['paths']['base_excel_file']
EXCEL_FILE_MAIN_PATH = os.path.join(os.path.normpath(EXCEL_FILE_DIRECTORY), BASE_EXCEL_FILE)

ORDERS_HEADERS = config['header_settings']['orders_headers']
HOLDINGS_HEADERS = config['header_settings']['holdings_headers']


# Misc
