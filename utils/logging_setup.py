"""Centralized logging configuration for RSAssistant.

Provides colored console output, file logging with rotation, and a
heartbeat writer for Docker health checks.
"""
import logging
import os
import sys
import time
from collections import OrderedDict
from logging.handlers import RotatingFileHandler
from datetime import datetime
from threading import Lock, Thread
from colorama import Fore, Style
from utils.config_utils import VOLUMES_DIR

_logging_lock = Lock()
_heartbeat_lock = Lock()
_heartbeat_started = False


class ReplaceInvalidCharactersFilter(logging.Filter):
    def filter(self, record):
        record.msg = "".join("?" if ord(c) > 127 else c for c in str(record.msg))
        return True


class TimeLengthListDuplicateFilter(logging.Filter):
    """Suppress repeated INFO/DEBUG messages; bounded by time and entry count.

    WARNING and above, and records tagged ``never_dedupe``, always pass through
    unmodified (no truncation) so failure diagnostics stay complete.
    """

    def __init__(
        self, interval=60, max_message_length=200, max_sample_items=5, max_entries=1024
    ):
        super().__init__()
        self.logged_messages = OrderedDict()
        self.interval = interval
        self.max_message_length = max_message_length
        self.max_sample_items = max_sample_items
        self.max_entries = max_entries

    def truncate_message(self, msg):
        msg_str = str(msg)
        return (
            msg_str
            if len(msg_str) <= self.max_message_length
            else f"{msg_str[: self.max_message_length]}... [truncated]"
        )

    def _evict(self, now):
        while self.logged_messages:
            key, ts = next(iter(self.logged_messages.items()))
            if now - ts >= self.interval or len(self.logged_messages) > self.max_entries:
                self.logged_messages.popitem(last=False)
            else:
                break

    def filter(self, record):
        if record.levelno >= logging.WARNING or getattr(record, "never_dedupe", False):
            return True
        now = time.time()
        message_text = record.getMessage()
        msg_key = hash(message_text)
        self._evict(now)
        last = self.logged_messages.get(msg_key)
        if last is not None and now - last < self.interval:
            return False
        self.logged_messages[msg_key] = now
        self.logged_messages.move_to_end(msg_key)
        self._evict(now)
        record.msg = self.truncate_message(message_text)
        record.args = ()
        return True


def start_heartbeat_writer(
    path=str(VOLUMES_DIR / "logs" / "heartbeat.txt"), interval=60
):
    global _heartbeat_started

    with _heartbeat_lock:
        if _heartbeat_started:
            return
        _heartbeat_started = True

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
    with _logging_lock:
        log_level = (
            "DEBUG"
            if verbose
            else config.get("logging", {}).get("level", "INFO").upper()
            if config
            else "INFO"
        )
        log_file = (
            config.get("logging", {}).get("file", str(VOLUMES_DIR / "logs" / "app.log"))
            if config
            else str(VOLUMES_DIR / "logs" / "app.log")
        )
        max_size = 10485760
        backup_count = (
            config.get("logging", {}).get("backup_count", 2) if config else 2
        )
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        root_logger = logging.getLogger()
        for existing_handler in root_logger.handlers[:]:
            root_logger.removeHandler(existing_handler)
            try:
                existing_handler.close()
            except Exception:
                pass

        handler = RotatingFileHandler(
            log_file, maxBytes=max_size, backupCount=backup_count
        )
        handler.setLevel(getattr(logging, log_level, logging.INFO))

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level, logging.INFO))
        try:
            if hasattr(console_handler.stream, "reconfigure"):
                console_handler.stream.reconfigure(encoding="utf-8")
        except Exception as e:
            logging.warning(f"Failed to set UTF-8 encoding for console: {e}")

        filter_invalid_chars = ReplaceInvalidCharactersFilter()
        for h in [handler, console_handler]:
            h.addFilter(filter_invalid_chars)

        root_logger.filters.clear()
        root_logger.addFilter(TimeLengthListDuplicateFilter())

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
                original = record.levelname
                record.levelname = f"{log_color}{original}{Style.RESET_ALL}"
                try:
                    return super().format(record)
                finally:
                    record.levelname = original

        console_handler.setFormatter(
            ColorFormatter(
                "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
        )

        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
            handlers=[handler, console_handler],
        )

        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("discord").setLevel(logging.WARNING)
        logging.info("Logging setup complete.")
        start_heartbeat_writer()


logger = logging.getLogger("RSAssistant")
