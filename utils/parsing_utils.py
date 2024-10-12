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

# Centralized function for standardizing broker names
def standardize_broker_name(broker_name):
    """Standardize broker names to a consistent format."""
    broker_name_mapping = {
        'WELLSFARGO': 'Wellsfargo',
        'SCHWAB': 'Schwab',
        'FIDELITY': 'Fidelity',
        'ROBINHOOD': 'Robinhood',
        'BBAE' : 'BBAE'
        # Add any other broker mappings as needed
    }

    # Return the mapped name, or capitalize properly if not in mapping
    return broker_name_mapping.get(broker_name.upper(), broker_name.capitalize())

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
    'schwab_failure': r"Schwab \d+ account (\w+): The order verification produced the following messages:",
    'chase_verification': r'(Chase)\s\d+\saccount\s(?:xxxx)?(\d+):\sThe order verification was successful',
    'firstrade_order': r"Firstrade \d+ (buying|selling) (\d+\.?\d*) ([A-Z]+) @ market",
    'firstrade_verification': r"Firstrade \d+ account\sxxxx(\d{4}):\sThe order verification was (successful|unsuccessful)",
    'firstrade_failure': r"Firstrade \d+ account (\w+): The order verification produced the following messages:",
    'bbae': r'(?i)(BBAE)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)'
}

def parse_order_message(content):
    """Parses an order message and extracts relevant details based on broker formats."""
    for broker, pattern in patterns.items():
        match = re.match(pattern, content)
        if match:
            if broker in ['schwab_order', 'chase_buy_sell', 'firstrade_order']:
                print(broker)
                handle_incomplete_order(match, broker)
            elif broker in ['schwab_verification', 'chase_verification', 'firstrade_verification']:
                print("Recieved verification message, handling...")
                handle_verification(match, broker)
            elif broker in  ['schwab_failure', 'firstrade_failure']:
                print("Received failure message, removing failed account...")
                handle_failed_order(match, broker)
            else:
                handle_complete_order(match, broker)
            return
    print(f"Failed to parse order message: {content}")

def handle_incomplete_order(match, broker):
    """Handles incomplete buy/sell orders for Chase, Schwab, and Firstrade."""
    try:
        # Print matched groups for debugging
        print(f"Matched groups for {broker}: {match.groups()}")

        # Handle brokers based on the expected groups
        if broker == 'schwab_order':
            action, quantity, stock = match.groups()[1:4]
        elif broker == 'chase_buy_sell':
            action, quantity, stock = match.groups()[1:4]
        elif broker == 'firstrade_order':
            action, quantity, stock = match.groups()[1:4]  # No need for [1:4] slicing here
        
        # Add fallback in case any of the variables are None
        if not action or not quantity or not stock:
            raise ValueError(f"Missing values: action={action}, quantity={quantity}, stock={stock}")

        # Account mapping logic
        account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
        
        if broker == 'schwab_order':
            for account in account_mapping.get('Schwab', []):
                incomplete_orders[(stock, account)] = {
                    'broker': 'Schwab', 'action': action, 'quantity': quantity, 'stock': stock
                }
                print(f"Saved account {account} order {action} {quantity} of {stock} as pending for {broker}")                    

        elif broker == 'chase_buy_sell':
            for account in account_mapping.get('Chase', []):
                incomplete_orders[(stock, account)] = {
                    'broker': 'Chase', 'action': action, 'quantity': quantity, 'stock': stock
                }        
                print(f"Saved account {account} order {action} {quantity} of {stock} as pending for {broker}")

        elif broker == 'firstrade_order':
            for account in account_mapping.get('Firstrade', []):
                incomplete_orders[(stock, account)] = {
                    'broker': 'Firstrade', 'action': action, 'quantity': quantity, 'stock': stock,
                    'account_number': 'Pending'  # Mark the account as pending
                }
                if account == 'Pending':
                    print(f"Saved account {account} order {action} {quantity} of {stock} as pending for {broker}")
                    
                else:
                    print(f"Account {account} pending order {action} {quantity} of {stock} for {broker}")

    except ValueError as e:
        print(f"Error in handle_incomplete_order: {e}")

def handle_verification(match, broker):
    """Processes order verification for Chase, Schwab, and Firstrade."""
    print(match, broker)
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
    account_number = match.groups()[0]
    print(account_number)
    
    if broker == 'schwab_verification':
        account_number = match.groups()[1]
        print(account_number)

        broker = 'Schwab'
        print(f"Verifying {broker}, account number: {account_number}, mapped list: {account_mapping.get('Schwab', [])}")
        process_verified_orders('Schwab', account_number, account_mapping.get('Schwab', []))
    
    elif broker == 'chase_verification':
        account_number = match.groups()[1]
        print(account_number)

        broker = 'Chase'
        print(f"Verifying {broker}, account number: {account_number}, mapped list: {account_mapping.get('Chase', [])}")
        process_verified_orders('Chase', account_number, account_mapping.get('Chase', []))
        
    elif broker == 'firstrade_verification':
        account_number = match.groups()[0]
        print(account_number)

        broker = 'Firstrade'
        print(f"Verifying {broker}, account number: {account_number}, mapped list: {account_mapping.get('Firstrade', [])}")
        process_verified_orders('Firstrade', account_number, account_mapping.get('Firstrade', []))

def process_verified_orders(broker, account_number, account_list, status=None):
    """Processes verified orders for the specified broker, including Firstrade."""
    print("Verifying orders...")
    for (stock, account), order in list(incomplete_orders.items()):
        if order['broker'] == broker and account in account_list:
            print(f"Verified order {order['action']} {order['quantity']} of {stock} for {broker} {account_number}")
            del incomplete_orders[(stock, account)]
            print(f"Removed {order['action']} order for {broker} {account_number}")
            save_order_to_csv(broker, account_number, order['action'], order['quantity'], stock)
            # print(f"List: {list(incomplete_orders.items())}")
            break    

def handle_complete_order(match, broker):
    """Handles complete buy and sell orders."""
    try:
        # Initialize the variables with default values
        account_number = None
        action = None
        quantity = None
        stock = None
        
        print(f"Processing order for broker: {broker}, match: {match.groups()}")

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
            if quantity == '1.0':
                action = 'sell'
            elif quantity == '99.0':
                action = 'buy'
                quantity = '1'
            elif quantity == '999.0':
                action = 'buy'
                quantity = '1'
            else:
                print("No quantity found.")
            print(action, quantity)
        elif broker == 'fennel':
            broker, group_number, action, quantity, stock, account_number = match.groups()[:6]
            account_number = f"{group_number}{account_number}"
        else:
            raise ValueError(f"Broker {broker} not recognized in complete order handler.")
    
        # If it's a sell order, mark it as pending closure
        if action == 'sell':
            update_watchlist(broker, account_number, stock, 0, order_type='sell')  # Use quantity=0 for pending closure

        save_order_to_csv(broker, account_number, action, quantity, stock)
        print(f"{broker}, Account {account_number}, {action.capitalize()} {quantity} of {stock}")
    except Exception as e:
        print(f"Error handling complete order: {e}")

def handle_failed_order(match, broker):
    try:
        # Extract the account number from the failure message
        account_number = match.group(1)
        
        # Loop through incomplete orders and remove the one matching the account number
        to_remove = []
        for (stock, account), order in incomplete_orders.items():
            if order['broker'] == 'Firstrade' and account == account_number:
                to_remove.append((stock, account))
                print(f"Removing Firstrade order for account {account_number} due to failure.")

        # Remove failed accounts from incomplete_orders
        for item in to_remove:
            del incomplete_orders[item]

    except Exception as e:
        print(f"Error handling failed order: {e}")

        
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
    broker_name = standardize_broker_name(embed.title.split(" Holdings")[0])

    for field in embed.fields:
        # Extract the account number and remove leading zeros
        if broker_name == 'WELLSFARGO':
            broker_name = 'Wellsfargo'
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
                update_watchlist(broker_name, account_nickname, stock, quantity)
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


