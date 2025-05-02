# === logging_setup.py (with Docker heartbeat and reconnect resilience) ===
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime
from threading import Thread
from colorama import Fore, Style


class ReplaceInvalidCharactersFilter(logging.Filter):
    def filter(self, record):
        record.msg = "".join("?" if ord(c) > 127 else c for c in str(record.msg))
        return True


def start_heartbeat_writer(path="./volumes/logs/heartbeat.txt", interval=60):
    def writer():
        while True:
            try:
                with open(path, "w") as f:
                    f.write(datetime.now().isoformat())
            except Exception as e:
                logging.warning(f"Heartbeat update failed: {e}")
            time.sleep(interval)

    Thread(target=writer, daemon=True).start()


def setup_logging(config=None, verbose=False):
    log_level = (
        "DEBUG"
        if verbose
        else config.get("logging", {}).get("level", "INFO").upper()
        if config
        else "INFO"
    )
    log_file = (
        config.get("logging", {}).get("file", "logs/app.log")
        if config
        else "volumes/logs/app.log"
    )
    max_size = 10485760
    backup_count = config.get("logging", {}).get("backup_count", 2) if config else 2
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logging.getLogger().handlers.clear()

    handler = RotatingFileHandler(log_file, maxBytes=max_size, backupCount=backup_count)
    handler.setLevel(getattr(logging, log_level, logging.INFO))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    try:
        if hasattr(console_handler.stream, "reconfigure"):
            console_handler.stream.reconfigure(encoding="utf-8")
        else:
            console_handler.stream = open(1, "w", encoding="utf-8", closefd=False)
    except Exception as e:
        print(f"Failed to set UTF-8 encoding for console: {e}")

    filter_invalid_chars = ReplaceInvalidCharactersFilter()
    for h in [handler, console_handler]:
        h.addFilter(filter_invalid_chars)

    class TimeLengthListDuplicateFilter(logging.Filter):
        def __init__(self, interval=60, max_message_length=200, max_sample_items=5):
            super().__init__()
            self.logged_messages = {}
            self.interval = interval
            self.max_message_length = max_message_length
            self.max_sample_items = max_sample_items

        def log_sample(self, data, label="Sample"):
            if isinstance(data, (list, tuple)):
                sample_data = data[: self.max_sample_items]
                logging.info(
                    f"{label} (up to {self.max_sample_items}): {sample_data}..."
                )
            elif isinstance(data, dict):
                sample_data = {
                    k: data[k] for k in list(data.keys())[: self.max_sample_items]
                }
                logging.info(
                    f"{label} (up to {self.max_sample_items}): {sample_data}..."
                )
            else:
                logging.info(f"{label}: {str(data)}")

        def truncate_message(self, msg):
            msg_str = str(msg)
            return (
                msg_str
                if len(msg_str) <= self.max_message_length
                else f"{msg_str[: self.max_message_length]}... [truncated]"
            )

        def filter(self, record):
            current_time = time.time()
            try:
                msg_key = hash(record.msg)
            except TypeError:
                if isinstance(record.msg, (list, dict)):
                    self.log_sample(record.msg, "Unhashable message")
                    return False
                msg_key = id(record.msg)
            if (
                msg_key in self.logged_messages
                and current_time - self.logged_messages[msg_key] < self.interval
            ):
                return False
            record.msg = self.truncate_message(record.msg)
            self.logged_messages[msg_key] = current_time
            return True

    logging.getLogger().addFilter(TimeLengthListDuplicateFilter())

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

    console_handler.setFormatter(
        ColorFormatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[handler, console_handler],
    )

    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.info("Logging setup complete.")
    start_heartbeat_writer()


logger = logging.getLogger("RSAssistant")
