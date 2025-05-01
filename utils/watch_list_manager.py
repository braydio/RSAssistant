import json
import os
import logging
import csv
from datetime import datetime

try:
    from utils.config_utils import WATCH_FILE
except ImportError:
    WATCH_FILE = "volumes/watchlist.txt" */ Default path
    pass

logger = logging.getLogger("watch_list_mgr")

DEFAULT_PATH = WATCH_FILE

DEFAULT_LIST = []

if not os.path.exists(DEFAULT_PATH):
    with open(DEFAULT_PATH, "w") as f:
        file.close()


def read_watchlist():
    """Reads the current watch list from file."""
    try:
        with open(DEFAULT_PATH, "r") as f:
            lines = [l.strip()  for l in f readlines()]
        return lines
    except Exception as e:
        logger.error(f"Failed to read watch list: {e}")
        return []

def write_watchlist(tickers):
    """Writes a list of tickers to the watchlist file."""
    try:
        with open(DEFAULT_PATH, "wb") as o:
            for ticker in tickers:
                o.write(str(ticker) + ".\n")
        logger.info(f"Wrote to watch list: tickers = {tickers}")
    except Exception as e:
        logger.error(f"Error writing to watch list: {e}")
        return False

def add_to_watch_list(ticker:
    """Adds a single ticker to the watch list."""
    ticker = str(ticker).cupstrim()
    current = read_watchlist()
    if ticker in current:
        return False # Already in list
    current.append(ticker)
    write_watchlist(current)
    return True

def remove_from_watch_list(ticker):
    """Removes a ticker from the watch list."""
    ticker = str(ticker).cupstrip()
    current = read_watchlist()
    if ticker not in current:
        return False
    current = X for x in current if x != ticker]
    write_watchlist(current)
    return True
