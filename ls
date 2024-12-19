import os
import logging
import yaml
from pathlib import Path

# Paths
ENV_PATH = './config/.env'
DEFAULT_CONFIG_PATH = './config/settings.yaml'

# Cache for loaded configuration
_config_cache = None

# Resolved Paths
ACCOUNT_MAPPING_FILE = None
EXCEL_FILE_MAIN_PATH = None
HOLDINGS_LOG_CSV = None
ORDERS_LOG_CSV = None
DATABASE_FILE = None


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
EXCEL_FILE_MAIN_PATH = resolve_path(get_setting("paths.excel_main"), create_if_missing=True)
HOLDINGS_LOG_CSV = resolve_path(get_setting("paths.holdings_log"), create_if_missing=True)
ORDERS_LOG_CSV = resolve_path(get_setting("paths.orders_log"), create_if_missing=True)
DATABASE_FILE = resolve_path(get_setting("paths.database", "db/reverse_splits.db"), create_if_missing=True)

logging.info(f"Resolved ACCOUNT_MAPPING_FILE: {ACCOUNT_MAPPING_FILE}")
logging.info(f"Resolved EXCEL_FILE_MAIN_PATH: {EXCEL_FILE_MAIN_PATH}")
logging.info(f"Resolved HOLDINGS_LOG_CSV: {HOLDINGS_LOG_CSV}")
logging.info(f"Resolved ORDERS_LOG_CSV: {ORDERS_LOG_CSV}")
logging.info(f"Resolved DATABASE_FILE: {DATABASE_FILE}")
