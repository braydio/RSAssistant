import re
import csv
import logging
import json
from discord import embeds
from datetime import datetime
from utils.csv_utils import save_order_to_csv, save_holdings_to_csv, read_holdings_log, get_holdings_for_summary
from utils.config_utils import load_config, get_account_nickname, load_account_mappings
from utils.watch_utils import update_watchlist

# Load configuration
config = load_config()
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']

# Order headers
ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Key', 'Broker Name', 'Account', 'Stock', 'Quantity', 'Price', 'Position Value', 'Account Total']

# Store incomplete orders
incomplete_orders = {}

# Regex patterns for various brokers
patterns = {
    'robinhood': r'(Robinhood)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'fidelity': r'(Fidelity)\s\d+\saccount\s(?:xxxxx)?(\d+):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
    'tradier': r'(Tradier)\saccount\s(?:xxxx)?(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+):\s(ok|failed)',
    'webull_buy': r'(Webull)\s\d+:\sbuying\s(\d+\.?\d*)\sof\s(\w+)',
    'wellsfargo': r'(WELLSFARGO)\s\d+\s\*\*\*(\d+):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
    'webull_sell': r'(Webull)\s\d+:\ssell\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\w+):\s(Success|Failed)',
    'fennel': r'(Fennel)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sAccount\s(\d+):\s(Success|Failed)',
    'public': r'(Public)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'schwab_order': r'(Schwab)\s\d+\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)',
    'chase_buy_sell': r'(Chase)\s\d+\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(LIMIT|MARKET)',
    'schwab_verification': r'(Schwab)\s\d+\saccount\s(?:xxxx)?(\d+):\sThe order verification was successful',
    'chase_verification': r'(Chase)\s\d+\saccount\s(?:xxxx)?(\d+):\sThe order verification was successful',
    'bbae': r'(?i)(BBAE)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)'
}

def parse_order_message(content):
    """Parses an order message and extracts relevant details based on broker formats."""
    for broker, pattern in patterns.items():
        match = re.match(pattern, content)
        if match:
            if broker in ['schwab_order', 'chase_buy_sell']:
                handle_incomplete_order(match, broker)
            elif broker in ['schwab_verification', 'chase_verification']:
                handle_verification(match, broker)
            else:
                handle_complete_order(match, broker)
            return
    print(f"Failed to parse order message: {content}")

def handle_incomplete_order(match, broker):
    """Handles incomplete buy/sell orders for Chase and Schwab."""
    action, quantity, stock, order_type = match.groups()[1:5]
    if action == 'selling':
        action = 'sell'
    elif action == 'buying':
        action = 'buy'
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
    
    if broker == 'schwab_order':
        # Handle Schwab orders
        for account in account_mapping.get('Schwab', []):
            incomplete_orders[(stock, account)] = {
                'broker': 'Schwab', 'action': action, 'quantity': quantity, 'stock': stock, 'order_type': order_type
            }
            print(account, order_type)
            save_order_to_csv('Schwab', account, action, quantity, stock)
    else:
        # Handle Chase orders
        for account in account_mapping.get('Chase', []):
            incomplete_orders[(stock, account)] = {
                'broker': 'Chase', 'action': action, 'quantity': quantity, 'stock': stock, 'order_type': order_type
            }
            save_order_to_csv('Chase', account, action, quantity, stock)

def handle_verification(match, broker):
    """Processes order verification for Chase and Schwab."""
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
    account_number = match.group(2)
    if broker == 'schwab_verification':
        process_verified_orders('Schwab', account_number, account_mapping.get('Schwab', []))
    elif broker == 'chase_verification':
        process_verified_orders('Chase', account_number, account_mapping.get('Chase', []))

def process_verified_orders(broker, account_number, account_list):
    """Processes verified orders for the specified broker."""
    for (stock, account), order in list(incomplete_orders.items()):
        if order['broker'] == broker and account in account_list:
            save_order_to_csv(broker, account_number, order['action'], order['quantity'], stock)
            del incomplete_orders[(stock, account)]

def handle_complete_order(match, broker):
    """Handles complete orders for brokers other than Schwab and Chase."""
    try:
        account_number = None
        if broker in ['robinhood', 'public', 'bbae']:
            broker, action, quantity, stock, account_number = match.groups()[:5]
        elif broker == 'webull_buy':
            broker, quantity, stock = match.groups()[:3]
            account_number = 'N/A'
            action = 'buy'
        elif broker == 'wellsfargo':
            broker_allcaps, account_number, action, quantity, stock = match.groups()[:5]
            broker = 'Wellsfargo'
        elif broker in ['fidelity', 'tradier']:
            broker, account_number, action, quantity, stock = match.groups()[:5]
        elif broker == 'webull_sell':
            broker, quantity, stock, account_number = match.groups()[:4]
            action = 'sell'
        elif broker == 'fennel':
            broker, group_number, action, quantity, stock, account_number = match.groups()[:6]
            account_number = f"{group_number}{account_number}"
        
        save_order_to_csv(broker, account_number, action, quantity, stock)
        print(f"{broker}, Account {account_number}, {action.capitalize()} {quantity} of {stock}")
    except Exception as e:
        print(f"Error handling complete order: {e}")
        
def parse_manual_order_message(content):
    """Parses a manual order message. Expected format: 'manual Broker Account OrderType Stock Price'"""
    try:
        parts = content.split()
        if len(parts) != 6:
            raise ValueError("Invalid format. Expected 'manual Broker Account OrderType Stock Price'.")
        
        return {
            'broker_name': parts[1],
            'account': parts[2],
            'order_type': parts[3],
            'stock': parts[4],
            'price': float(parts[5])
        }
    except Exception as e:
        print(f"Error parsing manual order: {e}")
        return None

def parse_embed_message(embed, holdings_log_file):
    broker_name = embed.title.split(" Holdings")[0]

    for field in embed.fields:
        # Extract the account number and remove leading zeros
        account_number = re.search(r'\((\w+)\)', field.name).group(1).lstrip('x') if re.search(r'\((\w+)\)', field.name) else field.name.lstrip('0')

        # Get the account nickname using the helper function
        account_nickname = get_account_nickname(broker_name, account_number)
        mapped_account = broker_name + " " + account_nickname
        account_key = mapped_account

        print(f"Account nickname: {account_nickname}")

        # Read existing holdings log
        existing_holdings = []
        with open(holdings_log_file, 'r') as file:
            csv_reader = csv.reader(file)
            existing_holdings = [row for row in csv_reader if row[0] != account_key]

        # Parse the new holdings from the message
        new_holdings = []
        account_total = None
        for line in field.value.splitlines():
            match = re.match(r"(\w+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line)
            if match:
                stock = match.group(1)
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append([account_key, broker_name, account_number, stock, quantity, price, total_value])
                update_watchlist(broker_name, account_nickname, stock)
            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

        # Append account total to all new holdings rows
        if account_total:
            for holding in new_holdings:
                holding.append(account_total)

        # Combine old and new holdings
        updated_holdings = existing_holdings + new_holdings

        # Write updated holdings to CSV
        with open(holdings_log_file, 'w', newline='') as file:
            csv_writer = csv.writer(file)
            csv_writer.writerows(updated_holdings)

        print(f"Updated holdings for {account_key}.")


