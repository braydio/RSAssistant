"""Configuration helpers and account mapping utilities.

This module loads environment variables, resolves file paths and provides
helper functions for broker account lookups. When an account nickname is not
found in the mapping JSON, :data:`DEFAULT_ACCOUNT_NICKNAME` is used to
construct a fallback based on broker, group and account numbers.

Set the ``VOLUMES_DIR`` environment variable to override the default
``volumes/`` directory path. This allows running the bot against external
storage mounts such as ``/mnt/netstorage/volumes``.
"""

import json
import os
from pathlib import Path

import dotenv

import logging

logger = logging.getLogger(__name__)

# --- Directories ---
UTILS_DIR = Path(__file__).resolve().parent
BASE_DIR = UTILS_DIR.parent
VOLUMES_DIR = Path(
    os.getenv("VOLUMES_DIR", str(BASE_DIR / "volumes"))
).resolve()
CONFIG_DIR = VOLUMES_DIR / "config"

# --- Config paths ---
ENV_PATH = CONFIG_DIR / ".env"
ACCOUNT_MAPPING = CONFIG_DIR / "account_mapping.json"
WATCH_FILE = CONFIG_DIR / "watch_list.json"
SELL_FILE = CONFIG_DIR / "sell_list.json"
EXCEL_FILE_MAIN = VOLUMES_DIR / "excel" / "ReverseSplitLog.xlsx"
HOLDINGS_LOG_CSV = VOLUMES_DIR / "logs" / "holdings_log.csv"
ORDERS_LOG_CSV = VOLUMES_DIR / "logs" / "orders_log.csv"
SQL_DATABASE = VOLUMES_DIR / "db" / "rsa_database.db"
ERROR_LOG_FILE = VOLUMES_DIR / "logs" / "error_log.txt"

ALPACA_API_SECRET = os.getenv("ALPACA_SECRET_KEY")  # Paper Account
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")  # Paper Account
BASE_URL = "https://paper-api.alpaca.markets/v2"  # Paper Account

# Default placeholder used when an account has no nickname in the mapping.
DEFAULT_ACCOUNT_NICKNAME = "{broker} {group} {account}"


# --- Load .env ---
def load_env():
    if ENV_PATH.exists():
        dotenv.load_dotenv(dotenv_path=ENV_PATH)
        logger.info(f"Environment variables loaded from {ENV_PATH}")
    else:
        logger.warning(f".env file not found at {ENV_PATH}")


load_env()

# --- Runtime constants from env ---
VERSION = "development 0.1"
DISCORD_PRIMARY_CHANNEL = int(os.getenv("DISCORD_PRIMARY_CHANNEL", 0))
DISCORD_SECONDARY_CHANNEL = int(os.getenv("DISCORD_SECONDARY_CHANNEL", 0))
DISCORD_AI_CHANNEL = int(os.getenv("DISCORD_AI_CHANNEL", 0))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# --- Logging setup ---

# --- Logging resolved paths ---
logger.info(f"Loaded BOT_TOKEN: {'Set' if BOT_TOKEN else 'Missing'}")
logger.info(f"Resolved EXCEL_FILE_MAIN_PATH: {EXCEL_FILE_MAIN}")
logger.info(f"Resolved HOLDINGS_LOG_CSV: {HOLDINGS_LOG_CSV}")
logger.info(f"Resolved ORDERS_LOG_CSV: {ORDERS_LOG_CSV}")
logger.info(f"Resolved DATABASE_FILE: {SQL_DATABASE}")
logger.info(f"Resolved ERROR_LOG: {ERROR_LOG_FILE}")
logger.info(f"Resolved WATCH_FILE: {WATCH_FILE}")
logger.info(f"Resolved SELLING_FILE: {SELL_FILE}")

ENABLE_TICKER_CLI = os.getenv("ENABLE_TICKER", False)
logger.info(f"Pricing fallback Ticker Enabled: {ENABLE_TICKER_CLI}")

# === Account Mapping Functions ===


def load_account_mappings():
    logger.debug(f"Loading account mappings from {ACCOUNT_MAPPING}")
    if not ACCOUNT_MAPPING.exists():
        logger.error(f"Account mapping file {ACCOUNT_MAPPING} not found.")
        return {}

    try:
        with open(ACCOUNT_MAPPING, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug(f"Account mapping data loaded successfully.")
            if not isinstance(data, dict):
                logger.error(
                    f"Invalid account mapping structure in {ACCOUNT_MAPPING}. Expected a dictionary."
                )
                return {}
            return data
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {ACCOUNT_MAPPING}: {e}")
        return {}


def save_account_mappings(mappings):
    logger.debug(f"Saving account mappings to {ACCOUNT_MAPPING}")
    with open(ACCOUNT_MAPPING, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=4)
    logger.info(f"Account mappings saved to {ACCOUNT_MAPPING}")


def get_broker_name(broker_number):
    mappings = load_account_mappings()
    for broker, accounts in mappings.items():
        if str(broker_number) in accounts:
            return broker
    return None


def get_broker_group(broker_name):
    mappings = load_account_mappings()
    return list(mappings.get(broker_name, {}).keys())


def get_account_number(broker_name, broker_number):
    mappings = load_account_mappings()
    return list(mappings.get(broker_name, {}).get(str(broker_number), {}).keys())


def get_account_nickname(broker_name, broker_number, account_number):
    """Return the nickname for an account or the formatted default."""

    mappings = load_account_mappings()
    nickname = (
        mappings.get(broker_name, {}).get(str(broker_number), {}).get(account_number)
    )

    if nickname:
        return nickname

    return DEFAULT_ACCOUNT_NICKNAME.format(
        broker=broker_name, group=broker_number, account=account_number
    )


def get_account_nickname_or_default(broker_name, broker_number, account_number):
    """Return nickname from mappings or the formatted default."""

    return get_account_nickname(broker_name, broker_number, account_number)


_config_cache = None


def load_config():
    """
    Load configuration from environment variables and static defaults.
    Replaces legacy YAML-based config loading.
    Returns a dictionary structured like the original YAML config for compatibility.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    _config_cache = {
        "general_settings": {
            "app_name": "RSAssistant",
            "file_version": "2.0",
        },
        "logging": {
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "file": os.getenv(
                "LOG_FILE",
                str(VOLUMES_DIR / "logs" / "rsassistant.log"),
            ),
            "backup_count": int(os.getenv("LOG_BACKUP_COUNT", 2)),
        },
        "environment": {
            "mode": os.getenv("ENV", "production"),
        },
        "discord": {
            "token": os.getenv("BOT_TOKEN", ""),
            "prefix": os.getenv("BOT_PREFIX", ".."),
            "primary_channel": int(os.getenv("DISCORD_PRIMARY_CHANNEL", 0)),
            "secondary_channel": int(os.getenv("DISCORD_SECONDARY_CHANNEL", 0)),
        },
        "heartbeat": {
            "enabled": os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true",
            "path": os.getenv(
                "HEARTBEAT_PATH",
                str(VOLUMES_DIR / "logs" / "heartbeat.txt"),
            ),
            "interval": int(os.getenv("HEARTBEAT_INTERVAL", 60)),
        },
    }

    return _config_cache
