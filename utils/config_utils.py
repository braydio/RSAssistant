"""Configuration helpers and account mapping utilities.

This module loads environment variables, resolves file paths and provides
helper functions for broker account lookups. When an account nickname is not
found in the mapping JSON, :data:`DEFAULT_ACCOUNT_NICKNAME` is used to
construct a fallback based on broker, group and account numbers. Missing
accounts are automatically persisted with this default mapping to keep
brokerage tracking functional without manual setup.

Set the ``VOLUMES_DIR`` environment variable to override the default
``volumes/`` directory path. This allows running the bot against external
storage mounts such as ``/mnt/netstorage/volumes``.
"""

import json
import os
from pathlib import Path

import dotenv

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Early path definitions for .env loading ---
UTILS_DIR = Path(__file__).resolve().parent
BASE_DIR = UTILS_DIR.parent
ENV_PATH = BASE_DIR / "config" / ".env"


# --- Load .env first ---
def load_env():
    """Load environment variables from a single, explicit source.

    Precedence:
    1. If `ENV_FILE` is set, load from that path only.
    2. If running in Docker (``/.dockerenv`` present), do not load any file
       and rely on process environment (e.g., compose `env_file`).
    3. Otherwise, load from `config/.env` when present.
    """

    # Explicit override wins and is the only file loaded
    env_file_override = os.getenv("ENV_FILE")
    if env_file_override:
        override_path = Path(env_file_override)
        if not override_path.is_absolute():
            override_path = (BASE_DIR / override_path).resolve()
        if override_path.exists():
            dotenv.load_dotenv(dotenv_path=override_path)
            logger.info(f"Environment variables loaded from ENV_FILE={override_path}")
        else:
            logger.warning(
                f"ENV_FILE set to {override_path} but file not found. Using process env only."
            )
        return

    # In Docker, rely on injected environment (compose env_file/environment)
    in_docker = Path("/.dockerenv").exists()
    if in_docker:
        logger.info(
            "Running in Docker; using process environment (no .env file loaded)"
        )
        return

    # Local dev default: config/.env
    if ENV_PATH.exists():
        dotenv.load_dotenv(dotenv_path=ENV_PATH)
        logger.info(f"Environment variables loaded from {ENV_PATH}")
    else:
        logger.warning(
            f".env file not found at {ENV_PATH}; using process environment only"
        )


load_env()

# --- Directories (after .env loaded) ---
VOLUMES_DIR = Path(os.getenv("VOLUMES_DIR", str(BASE_DIR / "volumes"))).resolve()
CONFIG_DIR = VOLUMES_DIR / "config"

# --- Config paths ---
ACCOUNT_MAPPING = CONFIG_DIR / "account_mapping.json"
WATCH_FILE = CONFIG_DIR / "watch_list.json"
SELL_FILE = CONFIG_DIR / "sell_list.json"
EXCEL_FILE_MAIN = VOLUMES_DIR / "excel" / "ReverseSplitLog.xlsx"
HOLDINGS_LOG_CSV = VOLUMES_DIR / "logs" / "holdings_log.csv"
ORDERS_LOG_CSV = VOLUMES_DIR / "logs" / "orders_log.csv"
SQL_DATABASE = VOLUMES_DIR / "db" / "rsa_database.db"
ERROR_LOG_FILE = VOLUMES_DIR / "logs" / "error_log.txt"

# --- Account nickname pattern ---
DEFAULT_ACCOUNT_NICKNAME = "{broker} {group} {account}"

# --- Runtime constants from env ---
VERSION = "development 0.1"
DISCORD_PRIMARY_CHANNEL = int(os.getenv("DISCORD_PRIMARY_CHANNEL", 0))
DISCORD_SECONDARY_CHANNEL = int(os.getenv("DISCORD_SECONDARY_CHANNEL", 0))
DISCORD_TERTIARY_CHANNEL = int(os.getenv("DISCORD_TERTIARY_CHANNEL", 0))
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_PREFIX = os.getenv("BOT_PREFIX", "..")

# --- Feature toggles and thresholds ---
# Automatically trigger holdings refresh when the watchlist reminder is sent
AUTO_REFRESH_ON_REMINDER = (
    os.getenv("AUTO_REFRESH_ON_REMINDER", "false").strip().lower() == "true"
)
# Threshold for triggering alerts on detected holdings based on last price
HOLDING_ALERT_MIN_PRICE = float(os.getenv("HOLDING_ALERT_MIN_PRICE", "1"))
# If enabled, automatically place sell orders to close detected holdings
AUTO_SELL_LIVE = os.getenv("AUTO_SELL_LIVE", "false").strip().lower() == "true"
# Comma-separated list of tickers to ignore for alerts/auto-sell
# Also supports a file of tickers (one per line) at CONFIG_DIR/ignore_tickers.txt
# or a custom path via IGNORE_TICKERS_FILE.

# Persistence layer toggles (enabled by default)
CSV_LOGGING_ENABLED = (
    os.getenv("CSV_LOGGING_ENABLED", "true").strip().lower() == "true"
)
EXCEL_LOGGING_ENABLED = (
    os.getenv("EXCEL_LOGGING_ENABLED", "true").strip().lower() == "true"
)
SQL_LOGGING_ENABLED = (
    os.getenv("SQL_LOGGING_ENABLED", "true").strip().lower() == "true"
)

# Path to ignore-tickers file (defaults to volumes/config/ignore_tickers.txt)
IGNORE_TICKERS_FILE = Path(
    os.getenv("IGNORE_TICKERS_FILE", str(CONFIG_DIR / "ignore_tickers.txt"))
).resolve()


def _load_ignore_tickers_from_file(path: Path) -> set:
    """Load tickers from a newline-delimited file, ignoring blanks and comments.

    Lines beginning with '#' are treated as comments. Whitespace is trimmed and
    tickers are normalized to uppercase.
    """
    tickers = set()
    try:
        if not path.exists():
            return tickers
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                # Allow optional inline comments with ' # '
                value = raw.split(" # ", 1)[0].strip()
                if value:
                    tickers.add(value.upper())
    except Exception as e:
        logger.error(f"Failed reading ignore tickers from {path}: {e}")
    return tickers


def _compute_ignore_tickers() -> set:
    """Combine env CSV IGNORE_TICKERS with file-based ignore list."""
    env_set = {
        t.strip().upper()
        for t in os.getenv("IGNORE_TICKERS", "").split(",")
        if t.strip()
    }
    file_set = _load_ignore_tickers_from_file(IGNORE_TICKERS_FILE)
    combined = env_set | file_set
    if combined:
        logger.info(
            f"Loaded {len(combined)} ignored tickers (env={len(env_set)}, file={len(file_set)} from {IGNORE_TICKERS_FILE})"
        )
    else:
        logger.info("No ignored tickers configured.")
    return combined


IGNORE_TICKERS = _compute_ignore_tickers()

# --- Mentions ---
# Discord user ID to mention in alerts (e.g., 123456789012345678)
MENTION_USER_ID = os.getenv("MENTION_USER_ID", os.getenv("MY_ID", "")).strip()
# Whether to include a mention on over-threshold alerts
MENTION_ON_ALERTS = os.getenv("MENTION_ON_ALERTS", "true").strip().lower() == "true"

# --- Logging resolved paths ---
logger.info(f"Loaded BOT_TOKEN: {'Set' if BOT_TOKEN else 'Missing'}")
logger.info(f"Resolved EXCEL_FILE_MAIN_PATH: {EXCEL_FILE_MAIN}")
logger.info(f"Resolved HOLDINGS_LOG_CSV: {HOLDINGS_LOG_CSV}")
logger.info(f"Resolved ORDERS_LOG_CSV: {ORDERS_LOG_CSV}")
logger.info(f"Resolved DATABASE_FILE: {SQL_DATABASE}")
logger.info(f"Resolved ERROR_LOG: {ERROR_LOG_FILE}")
logger.info(f"Resolved WATCH_FILE: {WATCH_FILE}")
logger.info(f"Resolved SELLING_FILE: {SELL_FILE}")

ENABLE_TICKER_CLI = os.getenv("ENABLE_TICKER", "false").strip().lower() == "true"
logger.info(f"Pricing fallback Ticker Enabled: {ENABLE_TICKER_CLI}")

# === Account Mapping Functions ===


def load_account_mappings():
    logger.debug(f"Loading account mappings from file path: {ACCOUNT_MAPPING}")
    if not ACCOUNT_MAPPING.exists():
        logger.error(f"Account mapping file {ACCOUNT_MAPPING} not found.")
        return {}

    try:
        with open(ACCOUNT_MAPPING, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                logger.error(
                    f"Invalid account mapping structure in {ACCOUNT_MAPPING}. Expected a dictionary."
                )
                return {}
            return data
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {ACCOUNT_MAPPING}: {e}")
        return {}


def save_account_mappings(mappings: dict) -> None:
    """Persist account nickname mappings to disk."""

    logger.debug(f"Saving account mappings to {ACCOUNT_MAPPING}")
    with open(ACCOUNT_MAPPING, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=4)
    logger.info(f"Account mappings saved to {ACCOUNT_MAPPING}")


def get_broker_name(broker_number: int | str) -> Optional[str]:
    """Return the broker name for ``broker_number`` if present."""

    mappings = load_account_mappings()
    for broker, accounts in mappings.items():
        if str(broker_number) in accounts:
            return broker
    return None


def get_broker_group(broker_name: str) -> list:
    """Return list of group numbers for ``broker_name``."""

    mappings = load_account_mappings()
    return list(mappings.get(broker_name, {}).keys())


def get_account_number(broker_name: str, broker_number: int | str) -> list:
    """Return account numbers under ``broker_name`` and ``broker_number``."""

    mappings = load_account_mappings()
    return list(mappings.get(broker_name, {}).get(str(broker_number), {}).keys())


def get_account_nickname(broker_name, broker_number, account_number):
    """Return the nickname for an account, creating a default mapping if missing.

    When an account is encountered without a user-defined nickname, a default
    nickname is generated using :data:`DEFAULT_ACCOUNT_NICKNAME` and persisted to
    :data:`ACCOUNT_MAPPING`. This ensures broker tracking commands function even
    before explicit account setup.
    """

    mappings = load_account_mappings()
    broker_str = str(broker_number)
    account_str = str(account_number)

    broker_dict = mappings.setdefault(broker_name, {})
    group_dict = broker_dict.setdefault(broker_str, {})

    nickname = group_dict.get(account_str)
    if nickname:
        return nickname

    nickname = DEFAULT_ACCOUNT_NICKNAME.format(
        broker=broker_name, group=broker_number, account=account_number
    )
    group_dict[account_str] = nickname
    save_account_mappings(mappings)
    return nickname


def get_account_nickname_or_default(broker_name, broker_number, account_number):
    """Return nickname from mappings or the formatted default."""

    return get_account_nickname(broker_name, broker_number, account_number)


_config_cache = None


def load_config():
    """
    Load configuration from environment variables and static defaults.
    Replaces legacy YAML-based config loading and exposes runtime
    persistence toggles for CSV, Excel, and SQL logging.
    Returns a dictionary structured like the original YAML config for
    compatibility.
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
        "persistence": {
            "csv": CSV_LOGGING_ENABLED,
            "excel": EXCEL_LOGGING_ENABLED,
            "sql": SQL_LOGGING_ENABLED,
        },
    }

    return _config_cache
