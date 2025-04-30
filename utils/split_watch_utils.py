import json
import os
import datetime

SPLIT_WATCH_FILE = "split_watchlist.json"

# Main data structure
data = {
    "watchlist": {}  # ticker -> {"split_date": "YYYY-MM-DD", "status": "buying"/"selling", "accounts_bought": [], "accounts_sold": []}
}


# Load/save utils
def load_data():
    global data
    if os.path.exists(SPLIT_WATCH_FILE):
        with open(SPLIT_WATCH_FILE, "r") as f:
            data = json.load(f)


def save_data():
    with open(SPLIT_WATCH_FILE, "w") as f:
        json.dump(data, f, indent=2)


# Add ticker on reverse split confirmation
def add_split_watch(ticker, split_date):
    ticker = ticker.upper()
    if ticker not in data["watchlist"]:
        data["watchlist"][ticker] = {
            "split_date": split_date,
            "status": "buying",
            "accounts_bought": [],
            "accounts_sold": [],
        }
        save_data()


# Mark account as holding ticker (buy confirmation)
def mark_account_bought(ticker, account_name):
    ticker = ticker.upper()
    if ticker in data["watchlist"]:
        if account_name not in data["watchlist"][ticker]["accounts_bought"]:
            data["watchlist"][ticker]["accounts_bought"].append(account_name)
            save_data()


# Move ticker to selling phase after split date
def update_split_status():
    today = datetime.date.today()
    for ticker, info in data["watchlist"].items():
        split_dt = datetime.datetime.strptime(info["split_date"], "%Y-%m-%d").date()
        if today >= split_dt and info["status"] == "buying":
            info["status"] = "selling"
    save_data()


# Mark account as having sold ticker (sell confirmation)
def mark_account_sold(ticker, account_name):
    ticker = ticker.upper()
    if ticker in data["watchlist"]:
        if account_name not in data["watchlist"][ticker]["accounts_sold"]:
            data["watchlist"][ticker]["accounts_sold"].append(account_name)
            save_data()


# Clean up completed tickers
def cleanup_completed_tickers():
    to_remove = []
    for ticker, info in data["watchlist"].items():
        if info["status"] == "selling":
            bought = set(info["accounts_bought"])
            sold = set(info["accounts_sold"])
            if bought and bought == sold:
                to_remove.append(ticker)
    for ticker in to_remove:
        del data["watchlist"][ticker]
    save_data()


# Query functions
def get_watchlist():
    return list(data["watchlist"].keys())


def get_status(ticker):
    return data["watchlist"].get(ticker.upper(), None)


def get_full_watchlist():
    """Returns the full watchlist dictionary."""
    return data.get("watchlist", {})


def get_all_accounts():
    """Returns a set of all known account names across the system. You can refine this later."""
    # For now, gather accounts seen in buy lists
    accounts = set()
    for ticker_info in data["watchlist"].values():
        accounts.update(ticker_info.get("accounts_bought", []))
    return accounts


# Initial load
load_data()
