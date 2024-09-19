import json
import os
import logging
from datetime import datetime
from collections import defaultdict
from utils.config_utils import load_config
from utils.excel_utils import add_stock_to_excel_log

# Load configuration and paths from settings
config = load_config()
WATCH_FILE = config['paths']['watch_list']
EXCEL_XLSX_FILE = config['paths']['excel_log']
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']

# Dictionary to track the watch list for specific tickers across accounts
watch_list = defaultdict(lambda: defaultdict(dict))

# Helper functions
def save_watch_list():
    """Save the current watch list to a JSON file."""
    with open(WATCH_FILE, 'w') as file:
        json.dump(watch_list, file, default=str)
    logging.info("Watch list saved.")

def load_watch_list():
    """Load the watch list from a JSON file."""
    global watch_list
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE, 'r') as file:
            watch_list.update(json.load(file))
        logging.info("Watch list loaded.")
    else:
        logging.info("No watch list file found, starting fresh.")

def update_watchlist_with_stock(ticker):
    """Adds a stock ticker to the Excel log."""
    ticker = ticker.upper()
    try:
        add_stock_to_excel_log(ticker, EXCEL_XLSX_FILE)
        logging.info(f"Successfully added {ticker} to the watchlist and Excel log.")
    except Exception as e:
        logging.error(f"Error updating watchlist: {e}")

def load_account_mappings(filename=ACCOUNT_MAPPING_FILE):
    """Load account mappings from a JSON file."""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from {filename}: {e}")
            return {}
    else:
        logging.error(f"Account mapping file {filename} not found.")
        return {}

# Main functions
async def watch_ticker(ctx, ticker: str):
    """Add a stock ticker to the watch list."""
    ticker = ticker.upper()
    if ticker not in watch_list:
        watch_list[ticker] = defaultdict(dict)
        update_watchlist_with_stock(ticker)
    await ctx.send(f"Watching {ticker} across all accounts.")
    save_watch_list()

def update_watch_list(broker, account_number, stock, action):
    """Update the status of a stock ticker based on an action (buy, hold, sell)."""
    stock = stock.upper()
    account_mapping = load_account_mappings()
    broker_name = broker.capitalize()
    account_nickname = account_mapping.get(broker_name, {}).get(account_number, account_number)

    if stock not in watch_list:
        return

    account_data = watch_list[stock].setdefault(broker_name, {}).setdefault(account_number, {
        'account': account_nickname,
        'state': 'waiting',
        'steps_completed': 0,
        'last_updated': None
    })

    action_mapping = {'buy': 1, 'holding': 2, 'sold': 3}
    if action in action_mapping and account_data['steps_completed'] < action_mapping[action]:
        account_data['state'] = action
        account_data['steps_completed'] = action_mapping[action]
        account_data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    save_watch_list()
    logging.info(f"Updated {stock} for {broker_name}: {account_data}")

async def get_watch_status(ctx, ticker: str):
    """Get the status of a specific stock ticker across all accounts."""
    ticker = ticker.upper()
    account_mapping = load_account_mappings()

    if ticker in watch_list:
        status = f"Status for {ticker}:\n"
        for broker_name, broker_accounts in account_mapping.items():
            total_accounts = len(broker_accounts)
            holding_count = sum(1 for acc_number in broker_accounts if watch_list[ticker][broker_name].get(acc_number, {}).get('steps_completed', 0) >= 2)

            if holding_count > 0:
                status += f"{broker_name}: Positionn in {holding_count} of {total_accounts} accounts\n"
            else:
                status += f"{broker_name}: No position in {total_accounts} accounts\n"

        await send_chunked_message(ctx, status)
    else:
        await ctx.send(f"{ticker} is not being watched.")

async def list_watched_tickers(ctx):
    """List all currently watched stock tickers."""
    if not watch_list:
        await ctx.send("No tickers are being watched.")
    else:
        tickers = ", ".join(watch_list.keys())
        await ctx.send(f"Currently watching: {tickers}")

async def watch_ticker_status(ctx, ticker: str):
    """Track the progress of a given ticker across all accounts."""
    ticker = ticker.upper()

    if ticker not in watch_list:
        await ctx.send(f"{ticker} is not being watched.")
        return

    total_accounts = sum(len(accounts) for accounts in watch_list[ticker].values())
    buy_count = sum(1 for accounts in watch_list[ticker].values() for acc in accounts.values() if acc['steps_completed'] >= 1)
    holding_count = sum(1 for accounts in watch_list[ticker].values() for acc in accounts.values() if acc['steps_completed'] >= 2)
    sold_count = sum(1 for accounts in watch_list[ticker].values() for acc in accounts.values() if acc['steps_completed'] == 3)

    progress_message = (
        f"**Progress for {ticker}:**\n"
        f"Accounts bought: {buy_count}/{total_accounts}\n"
        f"Accounts holding: {holding_count}/{total_accounts}\n"
        f"Accounts sold: {sold_count}/{total_accounts}"
    )

    await ctx.send(progress_message)

async def all_watching(ctx):
    """Get the status of all currently watched tickers."""
    if not watch_list:
        await ctx.send("No tickers are being watched.")
        return

    status_message = "**Current Watchlist Status**\n"

    for ticker, accounts in watch_list.items():
        total_accounts = sum(len(accounts) for accounts in accounts.values())
        bought_count = sum(1 for acc in accounts.values() for a in acc.values() if a.get('steps_completed', 0) >= 1)
        holding_count = sum(1 for acc in accounts.values() for a in acc.values() if a.get('steps_completed', 0) >= 2)
        sold_count = sum(1 for acc in accounts.values() for a in acc.values() if a.get('steps_completed', 0) == 3)

        status_message += (
            f"Ticker: **{ticker}**\n"
            f"  - Bought: {bought_count}/{total_accounts}\n"
            f"  - Holding: {holding_count}/{total_accounts}\n"
            f"  - Sold: {sold_count}/{total_accounts}\n\n"
        )

    await send_chunked_message(ctx, status_message)

async def stop_watching(ctx, ticker: str):
    """Stop watching a stock ticker across all accounts."""
    ticker = ticker.upper()

    if ticker in watch_list:
        del watch_list[ticker]
        save_watch_list()
        await ctx.send(f"Stopped watching {ticker} across all accounts.")
        logging.info(f"Stopped watching {ticker}.")
    else:
        await ctx.send(f"{ticker} is not being watched.")
        logging.info(f"{ticker} was not being watched.")

# Utility function to send messages in chunks if too long for Discord
async def send_chunked_message(ctx, message):
    """Send messages in chunks to avoid exceeding Discord's message length limit."""
    if len(message) > 2000:
        chunks = [message[i:i + 2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            await ctx.send(chunk)
    else:
        await ctx.send(message)
