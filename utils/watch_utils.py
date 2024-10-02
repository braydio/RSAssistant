import json
import os
import logging
import pandas as pd
import discord
from datetime import datetime
from collections import defaultdict
from utils.config_utils import load_config, get_account_nickname
from utils.excel_utils import add_stock_to_excel_log
from utils.utility_utils import send_large_message_chunks

# Load configuration and paths from settings
config = load_config()
WATCH_FILE = config['paths']['watch_list']
EXCEL_XLSX_FILE = config['paths']['excel_log']
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
excluded_brokers = config.get('excluded_brokers', {})

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
async def watch_ticker(ctx, ticker: str, split_date: str):
    """Add a stock ticker with a split date to the watch list."""
    ticker = ticker.upper()
    
    if ticker not in watch_list:
        watch_list[ticker] = {
            'split_date': split_date,
            'reminder_sent': False,
            'brokers': defaultdict(lambda: {
                'state': 'initial',  
                'last_updated': None
            })
        }
        add_stock_to_excel_log(ticker, EXCEL_XLSX_FILE)
        logging.info("Added stock to watchlist and passed to excel utils.")
    await ctx.send(f"Watching {ticker} with a reverse split date on {split_date}.")
    save_watch_list()

def update_watchlist(broker_name, account_nickname, stock):
    # Check if the stock is in the watchlist
    if stock.upper() in watch_list:
        # Access the watchlist entry for this ticker
        watchlist_entry = watch_list[stock.upper()]

        # Update the 'brokers' section with the broker and account
        if broker_name not in watchlist_entry['brokers']:
            watchlist_entry['brokers'][broker_name] = {}

        watchlist_entry['brokers'][broker_name][account_nickname] = {
            'state': 'has position',
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        print(f"Updated watchlist for {stock.upper()} with broker {broker_name} for account {account_nickname}.")
        save_watch_list()

def should_skip(broker, account_nickname):
    """Returns True if the broker and account_nickname should be skipped."""
    if broker in excluded_brokers and account_nickname in excluded_brokers[broker]:
        return True
    return False

async def check_watchlist_positions(ctx, show_accounts=False):
    """Check which brokers or accounts still need to purchase watchlist tickers."""
    today = datetime.now().strftime('%Y-%m-%d')
    account_mapping = load_account_mappings()

    reminders = []  # Store reminder messages
    for ticker, data in watch_list.items():
        split_date = data.get('split_date')
        split_date = datetime.strptime(split_date, '%m/%d').replace(year=datetime.now().year).strftime('%Y-%m-%d')

        if split_date >= today:
            ticker_reminders = []  # Stores details per ticker
            print(f"Checking ticker {ticker} with split date {split_date}")

            for broker, accounts in account_mapping.items():
                watchlist_broker_accounts = data.get('brokers', {}).get(broker, {})
                print(f"Broker in watchlist: {broker}, Accounts in watchlist for broker: {watchlist_broker_accounts}")

                account_reminders = []
                for account in accounts:
                    account_nickname = get_account_nickname(broker, account)

                    # Skip accounts in the excluded list
                    if should_skip(broker, account_nickname):
                        continue

                    account_data = watchlist_broker_accounts.get(account_nickname, {})
                    account_state = account_data.get('state', 'waiting')

                    if account_state == 'waiting':
                        account_reminders.append(account_nickname)

                if account_reminders:
                    if show_accounts:
                        account_list = ", ".join(account_reminders)
                        ticker_reminders.append(f"Broker: {broker} | Accounts: {account_list}")
                    else:
                        ticker_reminders.append(f"Broker: {broker}")

            if ticker_reminders:
                reminders.append(f"Yet to purchase {ticker}:\n" + "\n".join(ticker_reminders))

    if reminders:
        reminder_message = "\n\n".join(reminders)
        await send_large_message_chunks(ctx, reminder_message)
    else:
        await ctx.send("All accounts have purchased the necessary stocks.")


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
                status += f"{broker_name}: Position in {holding_count} of {total_accounts} accounts\n"
            else:
                status += f"{broker_name}: No position in {total_accounts} accounts\n"

        await send_chunked_message(ctx, status)
    else:
        await ctx.send(f"{ticker} is not being watched.")

async def list_watched_tickers(ctx):
    """List all currently watched stock tickers with their split dates in a nicely formatted table."""
    if not watch_list:
        await ctx.send("No tickers are being watched.")
    else:
        # Header
        message = "```\n"  # Use code block for monospace formatting
        message += "Ticker   | Split Date\n"
        message += "---------|------------\n"
        
        # Rows of tickers and split dates
        for ticker, data in watch_list.items():
            split_date = data.get('split_date', 'N/A')
            message += f"{ticker:<8} | {split_date}\n"
        
        message += "```"  # End code block
        await ctx.send(message)

async def list_watched_tickers_embed(ctx):
    """List all currently watched stock tickers with their split dates using an embed."""
    if not watch_list:
        await ctx.send("No tickers are being watched.")
    else:
        embed = discord.Embed(
            title="Watchlist",
            description="Stocks being watched and their split dates",
            color=discord.Color.blue()
        )
        
        for ticker, data in watch_list.items():
            split_date = data.get('split_date', 'N/A')
            embed.add_field(name=f"{ticker}", value=f"Split Date: {split_date}", inline=False)
        
        await ctx.send(embed=embed)

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

# In progress:

async def watch_ticker_status(ctx, ticker: str):
    """Track the progress of a ticker across all accounts."""
    ticker = ticker.upper()

    if ticker not in watch_list:
        await ctx.send(f"{ticker} is not being watched.")
        return

    total_accounts = sum(len(accounts) for accounts in watch_list[ticker]['brokers'].values())
    buy_count = sum(1 for accounts in watch_list[ticker]['brokers'].values() for acc in accounts.values() if acc['steps_completed'] >= 1)

    progress_message = (
        f"**Progress for {ticker}:**\n"
        f"Accounts bought: {buy_count}/{total_accounts}\n"
        f"Split date: {watch_list[ticker]['split_date']}\n"
    )
    await ctx.send(progress_message)
