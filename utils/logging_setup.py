import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

from colorama import Fore, Style


class ReplaceInvalidCharactersFilter(logging.Filter):
    """
    A logging filter to replace invalid characters (e.g., emojis) in log messages.
    """
    def filter(self, record):
        # Replace invalid characters with a '?'
        record.msg = ''.join(
            '?' if ord(c) > 127 else c for c in str(record.msg)
        )
        return True

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
    max_size = 10485760
    backup_count = config.get("logging", {}).get("backup_count", 2) if config else 2

    # Ensure the logs directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Clear existing handlers to avoid duplicate logs
    logging.getLogger().handlers.clear()

    # Set up file handler
    handler = RotatingFileHandler(log_file, maxBytes=max_size, backupCount=backup_count)
    handler.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Set up console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))

    # Force UTF-8 encoding for the console output
    try:
        # For Python 3.7+ with `reconfigure`
        if hasattr(console_handler.stream, "reconfigure"):
            console_handler.stream.reconfigure(encoding="utf-8")
        else:
            # Fallback for older versions of Python
            console_handler.stream = open(1, "w", encoding="utf-8", closefd=False)
    except Exception as e:
        print(f"Failed to set UTF-8 encoding for console: {e}")

    # Add the ReplaceInvalidCharactersFilter
    filter_invalid_chars = ReplaceInvalidCharactersFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(filter_invalid_chars)


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

    logging.info("Logging setup complete.")


def setup_logging_no_dedup(config=None, verbose=False):
    """
    Similar to setup_logging, but logs to a separate file
    WITHOUT the deduplication filter.
    """
    log_level = (
        "DEBUG" if verbose
        else (config.get("logging", {}).get("level", "INFO").upper() if config else "INFO")
    )
    # Use a different file path so it doesn't conflict with the main log
    log_file = (
        config.get("logging", {}).get("file_no_dedup", "logs/app_no_dedup.log")
        if config
        else "volumes/logs/app_no_dedup.log"
    )
    max_size = int(config.get("logging", {}).get("max_size", 10485760)) if config else 10485760
    backup_count = config.get("logging", {}).get("backup_count", 2) if config else 2

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Create a fresh logger for this function so it doesn't conflict with the main logger
    logger_no_dedup = logging.getLogger("no_dedup_logger")
    logger_no_dedup.setLevel(getattr(logging, log_level, logging.INFO))
    logger_no_dedup.handlers.clear()  # ensure no duplication

    # File handler
    handler = RotatingFileHandler(log_file, maxBytes=max_size, backupCount=backup_count)
    handler.setLevel(getattr(logging, log_level, logging.INFO))

    # Console handler if you still want console output with color
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))

    # Try forcing UTF-8 in console
    try:
        if hasattr(console_handler.stream, "reconfigure"):
            console_handler.stream.reconfigure(encoding="utf-8")
        else:
            console_handler.stream = open(1, "w", encoding="utf-8", closefd=False)
    except Exception as e:
        print(f"Failed to set UTF-8 encoding for console: {e}")

    # Add a filter to replace invalid chars if desired
    filter_invalid_chars = ReplaceInvalidCharactersFilter()
    handler.addFilter(filter_invalid_chars)
    console_handler.addFilter(filter_invalid_chars)

    # *** Notice: We do NOT add the TimeLengthListDuplicateFilter here. ***

    # Set up color formatter for console if desired
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
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    # Add handlers
    logger_no_dedup.addHandler(handler)
    logger_no_dedup.addHandler(console_handler)

    # Example: if you want less chatty logs from third parties
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)

    logger_no_dedup.info("No-dedup logging setup complete.")
    return logger_no_dedup
