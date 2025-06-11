# === logging_setup.py (with Docker heartbeat and reconnect resilience) =
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from datetime import datetime
from threading import Thread
from colorama import Fore, Style

logger = logging.getLogger("RSAssistant")


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
                logger.warning(f"Heartbeat update failed: {e}")
            time.sleep(interval)

    Thread(target=writer, daemon=True).start()


class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        reset = Style.RESET_ALL
        record.msg = f"{color}{record.msg}{reset}"
        return super().format(record)


class TimeLengthListDuplicateFilter(logging.Filter):
    def __init__(self, interval=60, max_message_length=200, max_sample_items=5):
        super().__init__()
        self.logged_messages = {}
        self.interval = interval
        self.max_message_length = max_message_length
        self.max_sample_items = max_sample_items

    def filter(self, record):
        current_time = time.time()
        try:
            msg_key = hash(record.msg)
        except TypeError:
            msg_key = id(record.msg)

        if (
            msg_key in self.logged_messages
            and current_time - self.logged_messages[msg_key] < self.interval
        ):
            return False

        record.msg = self.truncate_message(record.msg)
        self.logged_messages[msg_key] = current_time
        return True

    def truncate_message(self, msg):
        msg_str = str(msg)
        if len(msg_str) <= self.max_message_length:
            return msg_str
        return f"{msg_str[: self.max_message_length]}... [truncated]"


def setup_logging(verbose=False):
    log_level = "DEBUG" if verbose else "INFO"
    log_file = "volumes/logs/rsassistant.log"
    max_size = 10 * 1024 * 1024  # 10 MB
    backup_count = 2

    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger.handlers.clear()

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

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(funcName)s() - %(message)s"
    )

    handler.setFormatter(formatter)
    console_handler.setFormatter(
        ColoredFormatter("%(asctime)s - %(levelname)s - %(message)s")
    )


    filter_invalid = ReplaceInvalidCharactersFilter()
    duplicate_filter = TimeLengthListDuplicateFilter()

    for h in [handler, console_handler]:
        h.addFilter(filter_invalid)
        h.addFilter(duplicate_filter)

    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.addHandler(handler)
    logger.addHandler(console_handler)

    logger.info("Logging setup complete.")

    # Start heartbeat
    start_heartbeat_writer()
    logger.info("Heartbeat writer started at ./volumes/logs/heartbeat.txt every 60s.")
