import json
import os
from datetime import datetime
from utils.logging_setup import logger

sell_list = {}
executed_sell_list = {}

SELL_LIST_FILE = "data/sell_list.json"
EXECUTED_SELL_LIST_FILE = "data/executed_sell_list.json"


def load_sell_list():
    global sell_list
    if os.path.exists(SELL_LIST_FILE):
        with open(SELL_LIST_FILE, "r") as f:
            sell_list = json.load(f)
    else:
        sell_list = {}


def save_sell_list():
    with open(SELL_LIST_FILE, "w") as f:
        json.dump(sell_list, f, indent=2)


def save_executed_list():
    with open(EXECUTED_SELL_LIST_FILE, "w") as f:
        json.dump(executed_sell_list, f, indent=2)


def load_executed_list():
    global executed_sell_list
    if os.path.exists(EXECUTED_SELL_LIST_FILE):
        with open(EXECUTED_SELL_LIST_FILE, "r") as f:
            executed_sell_list = json.load(f)
    else:
        executed_sell_list = {}


def is_ticker_watched(ticker: str) -> bool:
    ticker = ticker.upper()
    return ticker in get_watch_list()  # or whatever data structure you're using

def add_to_sell_list(ticker: str, broker: str = "all", quantity: float = 1.0, scheduled_time: str = None):
    """Adds a ticker to the sell list if not already present."""
    ticker = ticker.upper()

    if ticker in sell_list:
        logger.info(f"{ticker} already exists in sell list. Skipping add.")
        return False

    if not scheduled_time:
        scheduled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sell_list[ticker] = {
        "broker": broker,
        "quantity": quantity,
        "scheduled_time": scheduled_time,
        "added_on": scheduled_time,
    }
    save_sell_list()
    logger.info(f"Added {ticker} to sell list.")
    return True


def remove_from_sell_list(ticker: str):
    ticker = ticker.upper()
    if ticker in sell_list:
        del sell_list[ticker]
        save_sell_list()
        return True
    return False


def get_sell_list():
    return sell_list


def get_executed_list():
    return executed_sell_list
