import csv
import json
import logging
import re
from datetime import datetime

from discord import embeds

from utils.config_utils import (account_mapping, get_account_nickname, load_account_mappings,
                                load_config, get_last_stock_price)
from utils.csv_utils import (save_holdings_to_csv, save_order_to_csv)

# Load configuration
config = load_config()
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']

# Order headers
ORDERS_HEADERS = config['header_settings']['orders_headers']
HOLDINGS_HEADERS = config['header_settings']['holdings_headers']


# Store incomplete orders
incomplete_orders = {}

order_patterns = {
    'complete': {
        'BBAE': r'(BBAE)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)',
        'Fennel': r'(Fennel)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sAccount\s(\d+):\s(Success|Failed)',
        'Public': r'(Public)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)',
        'Robinhood': r'(Robinhood)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)',
        'WELLSFARGO': r'(WELLSFARGO)\s(\d+)\s\*\*\*(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
        'Fidelity': r'(Fidelity)\s(\d+)\saccount\s(?:xxxxx)?(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
        'Webull': r'(Webull)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sxxxx(\w+):\s(Success|Failed)',
        'DSPAC': r'(DSPAC)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)',
        'Plynk': r'(Plynk)\s(\d+)\sAccount\s(?P<account_number>\d{4}) (?P<action>buy|sell) (?P<stock>\w+)'

    },
    'incomplete': {
        'Schwab': r'(Schwab)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)',
        'Firstrade': r'(Firstrade)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)',
        'Vanguard': r'(Vanguard)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)',
        'Chase': r'(Chase)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(LIMIT|MARKET)',
        'Tradier': r'(Tradier)\s(\d+):\s(buying|selling)\s(\d+\.?\d*)\sof\s([A-Z]+)'
    },
    'verification': {
        'Schwab': r'(Schwab)\s(\d+)\saccount\sxxxx(\d{4}):\sThe\sorder\sverification\swas\ssuccessful',
        'Firstrade': r'(Firstrade)\s(\d+)\saccount\sxxxx(\d{4}):\sThe\sorder\sverification\swas\ssuccessful',
        'Vanguard': r'(Vanguard)\s(\d+)\saccount\sxxxx(\d{4}):\sThe\sorder\sverification\swas\ssuccessful',
        'Chase': r'(Chase)\s(\d+)\saccount\s(\d{4}):\sThe\sorder\sverification\swas\ssuccessful',
        'Tradier': r'(Tradier)\s(\d+)\saccount\sxxxx(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+):\s(ok|failed)',
        'Webull': r'(Webull)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sxxxx(\w+):\s(Success|Failed)'
    }
}

def normalize_order_data(broker_name, broker_number, action, quantity, stock, account_number):
    """Ensures consistent formatting of order data and applies special cases for specific brokers."""
    # Capitalize broker name properly, except for 'BBAE' and 'DSPAC'
    if broker_name not in ['BBAE', 'DSPAC']:
        broker_name = broker_name.capitalize()

    # Standardize action to 'buy' or 'sell' only if it’s not None
    if action:
        if action.lower() == 'buying':
            action = 'buy'
        elif action.lower() == 'selling':
            action = 'sell'
        else:
            action = action.lower()

    # Special case for Webull: if action is 'sell' with quantity 99.0 or 999.0, convert to 'buy' with quantity 1.0
    if broker_name.lower() == 'webull' and action == 'sell' and quantity in {99.0, 999.0}:
        action = 'buy'
        quantity = 1.0
        print("Webull 100/0 Lot Order: Action changed to 'buy' and quantity changed to 1.0")

    # Convert broker number and account number to strings for consistency
    broker_number = str(broker_number)
    account_number = str(account_number).zfill(4)  # Ensure account number is zero-padded to 4 digits

    # Ensure quantity is a float
    quantity = float(quantity)

    return broker_name, broker_number, action, quantity, stock, account_number

def handle_complete_order(match, broker_name, broker_number):
    """Processes complete buy/sell orders after normalization and saves to CSV."""
    try:
        # Extract fields based on broker type
        if broker_name == 'BBAE':
            account_number = match.group(6)
            action = match.group(3)
            quantity = match.group(4)
            stock = match.group(5)
        
        elif broker_name.lower() in {'fennel', 'public', 'robinhood', 'dspac'}:
            account_number = match.group(6)
            action = match.group(3)
            quantity = match.group(4)
            stock = match.group(5)
        
        elif broker_name == 'WELLSFARGO':
            account_number = match.group(3)
            action = match.group(4)
            quantity = match.group(5)
            stock = match.group(6)
        
        elif broker_name.lower() == 'fidelity':
            account_number = match.group(3)
            action = match.group(4)
            quantity = match.group(5)
            stock = match.group(6)
        
        elif broker_name.lower() == 'webull':
            account_number = match.group(6)
            action = match.group(3)
            quantity = float(match.group(4))
            stock = match.group(5)
            
            # Apply the special case for Webull orders
            if action.lower() == 'sell' and quantity in {99.0, 999.0}:
                action = 'buy'
                quantity = 1.0
                print("Special case for Webull: Changed action to 'buy' and quantity to 1.0")

        else:
            print(f"Unknown broker format for: {broker_name}")
            return

        # Normalize data
        broker_name, broker_number, action, quantity, stock, account_number = normalize_order_data(
            broker_name, broker_number, action, quantity, stock, account_number
        )

        # Get price and current date
        price = get_last_stock_price(stock)
        date = datetime.now().strftime('%Y-%m-%d')  # Use date only, no time

        # Create the order_data dictionary without Timestamp
        order_data = {
            'Broker Name': broker_name,
            'Broker Number': broker_number,
            'Account Number': account_number,
            'Order Type': action.capitalize(),
            'Stock': stock,
            'Quantity': quantity,
            'Price': price,
            'Date': date
        }

        # Save the order data to CSV
        save_order_to_csv(order_data)
        print(f"Saved complete order for {broker_name} {broker_number} to CSV")

    except Exception as e:
        print(f"Error handling complete order: {e}")

def handle_incomplete_order(match, broker_name, broker_number):
    """Sets up temporary entries for verification of incomplete orders."""
    try:
        action = match.group(3)
        quantity = match.group(4)
        stock = match.group(5)

        # Normalize data
        broker_name, broker_number, action, quantity, stock, _ = normalize_order_data(
            broker_name, broker_number, action, quantity, stock, None
        )

        print(f"Initializing temporary order for {broker_name} {broker_number}: {action} {quantity} of {stock}")
        # account_mapping = load_account_mappings(ACCOUNT_MAPPING)
        broker_accounts = account_mapping.get(broker_name, {}).get(str(broker_number))
        if broker_accounts:
            for account, nickname in broker_accounts.items():
                incomplete_orders[(stock, account)] = {
                    'broker_name': broker_name,
                    'broker_number': broker_number,
                    'account_number': account,
                    'nickname': nickname,
                    'action': action,
                    'quantity': quantity,
                    'stock': stock
                }
                print(f"Temporary order created for {nickname} - Account ending {account}")
        else:
            print(f"No accounts found for broker {broker_name} number {broker_number}")

    except Exception as e:
        print(f"Error in handle_incomplete_order: {e}")

def handle_verification(match, broker_name, broker_number):
    """Processes order verification and finalizes incomplete orders."""
    try:
        # Extract fields based on broker type for verification
        if broker_name.lower() == 'schwab':
            account_number = match.group(3)
            action = None  # Action is not specified in Schwab verification messages

        elif broker_name.lower() == 'firstrade':
            account_number = match.group(3)
            action = None  # Action is not specified in Firstrade verification messages

        elif broker_name.lower() == 'vanguard':
            account_number = match.group(3)
            action = None  # Action is not specified in Vanguard verification messages

        elif broker_name.lower() == 'chase':
            account_number = match.group(3)
            action = None  # Action is not specified in Chase verification messages

        elif broker_name.lower() == 'tradier':
            account_number = match.group(3)
            action = match.group(4).lower()  # Action (buy/sell) is specified in Tradier messages

        elif broker_name.lower() == 'webull':
            account_number = match.group(3)
            action = match.group(4).lower()  # Action (buy/sell) is specified in Webull messages

        else:
            print(f"Unknown broker format for verification: {broker_name}")
            return

        # Normalize data
        broker_name, broker_number, action, _, _, account_number = normalize_order_data(
            broker_name, broker_number, action, 1, '', account_number
        )

        print(f"Verification received for {broker_name} {broker_number}, Account {account_number}")

        # Check for matching incomplete orders and finalize them upon verification
        for key, order in list(incomplete_orders.items()):
            if (order['broker_name'] == broker_name and
                order['broker_number'] == broker_number and
                order['account_number'] == account_number and
                (action is None or order['action'] == action)):

                # Process and remove the verified order
                process_verified_orders(broker_name, account_number, order)
                del incomplete_orders[key]
                print(f"Verified and removed temporary order for Account {account_number}")
                break
        else:
            print(f"No matching temporary order found for {broker_name} {broker_number}, Account {account_number}")

    except Exception as e:
        print(f"Error in handle_verification: {e}")

def process_verified_orders(broker_name, account_number, order):
    """Processes and finalizes a verified order by passing it to handle_complete_order."""
    print(f"Verified order processed for {broker_name}, Account {account_number}:")

    # Call handle_complete_order to complete and save the order to CSV
    handle_complete_order(
        broker_name,
        order['broker_number'],
        account_number,
        order['action'],
        order['quantity'],
        order['stock']
    )
    print("Order has been finalized and saved to CSV.")

def parse_order_message(content):
    """Parses incoming messages and routes them to the correct handler based on type."""
    for order_type, patterns in order_patterns.items():
        for broker_name, pattern in patterns.items():
            match = re.match(pattern, content, re.IGNORECASE)
            if match:
                broker_name = match.group(1)
                broker_number = match.group(2)
                
                # Route to the correct handler based on the type
                if order_type == 'complete':
                    handle_complete_order(match, broker_name, broker_number)
                elif order_type == 'incomplete':
                    handle_incomplete_order(match, broker_name, broker_number)
                elif order_type == 'verification':
                    handle_verification(match, broker_name, broker_number)
                return  # Exit once a match is found
    
    print(f"No match found for message: {content}")


def handle_failed_order(match, broker_name, broker_number):
    """Handles failed orders by removing incomplete entries."""
    try:
        account_number = match.group(1)
        to_remove = [(stock, account) for (stock, account), order in incomplete_orders.items()
                     if order['broker'] == broker_name and account == account_number]
        
        for item in to_remove:
            del incomplete_orders[item]
            print(f"Removed failed order for {broker_name} {account_number}")

    except Exception as e:
        print(f"Error handling failed order: {e}")

from datetime import datetime

def parse_manual_order_message(content):
    """Parses a manual order message and formats it for order processing.
    Expected format: 'manual Broker BrokerNumber Account OrderType Stock Price'
    """
    try:
        parts = content.split()
        if len(parts) != 7:
            raise ValueError("Invalid format. Expected 'manual Broker BrokerNumber Account OrderType Stock Price'.")

        # Extract and format parts
        broker_name = parts[1]
        broker_number = parts[2].replace(":", "")   # Remove colon from Broker Number
        account_number = parts[3].replace(":", "")  # Remove colon from Account Number
        action = parts[4].capitalize()              # Capitalize order type (Buy/Sell)
        stock = parts[5].upper()                    # Stock ticker symbol in uppercase
        price = float(parts[6])                     # Convert Price to float
        quantity = 1.0                              # Default quantity for manual orders

        # Current date in YYYY-MM-DD format
        date = datetime.now().strftime('%Y-%m-%d')

        # Normalize data
        broker_name, broker_number, action, quantity, stock, account_number = normalize_order_data(
            broker_name, broker_number, action, quantity, stock, account_number
        )

        # Structure the parsed data as order_data
        order_data = {
            'Broker Name': broker_name,
            'Broker Number': broker_number,
            'Account Number': account_number,
            'Order Type': action,
            'Stock': stock,
            'Quantity': quantity,
            'Price': price,
            'Date': date
        }
        
        save_order_to_csv(order_data)
    
    except Exception as e:
        print(f"Error parsing manual order: {e}")
        return None



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

# -- Parsing Messages for Account Holdings


def parse_embed_message(embed):
    """
    Handles a new order message by parsing it and saving the holdings to CSV.
    """
    # Step 1: Parse the holdings from the embed message
    parsed_holdings = main_embed_message(embed)
    # Step 2: Save the parsed holdings to CSV
    save_holdings_to_csv(parsed_holdings)

    print("Holdings have been successfully parsed and saved.")


def main_embed_message(embed):
    """
    Parses an embed message based on the broker name.
    Dispatches to specific handler functions or general handler based on broker.
    Returns parsed holdings data.
    """
    broker_name = embed.fields[0].name.split(' ')[0]

    if broker_name.lower() == 'webull':
        return parse_webull_embed_message(embed)
    elif broker_name.lower() == 'fennel':
        return parse_fennel_message(embed)
    else:
        return parse_general_embed_message(embed)


def parse_general_embed_message(embed):
    """
    Parses an embed message and returns parsed holdings data for general brokers.
    """
    parsed_holdings = []

    for field in embed.fields:
        name_field = field.name
        value_field = field.value
        embed_split = name_field.split(' ')
        broker_name = embed_split[0]
       
               # Correct capitalization for specific brokers
        if broker_name.upper() == 'WELLSFARGO':
            broker_name = 'Wellsfargo'
        elif broker_name.upper() == 'VANGUARD':
            broker_name = 'Vanguard'

        group_number = embed_split[1] if len(embed_split) > 1 else '1'
        account_number_match = re.search(r'x+(\d+)', name_field)

        if not account_number_match:
            account_number_match = re.search(r'\((\d+)\)', name_field)

        account_number = account_number_match.group(1) if account_number_match else None

        if not account_number:
            continue

        account_nickname = get_account_nickname_or_default(broker_name, group_number, account_number)
        account_key = f"{broker_name} {account_nickname}"

        new_holdings = []
        account_total = None
        for line in value_field.splitlines():
            if "No holdings in Account" in line:
                continue
            match = re.match(r"([\w\s]+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line)
            if match:
                stock = match.group(1).strip()
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append([account_key, broker_name, group_number, account_number, stock, quantity, price, total_value])

            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

        if account_total:
            for holding in new_holdings:
                holding.append(account_total)

        parsed_holdings.extend(new_holdings)
        print(parsed_holdings)

    return parsed_holdings


def parse_webull_embed_message(embed):
    """
    Parses an embed message and returns parsed holdings data for Webull accounts.
    """
    parsed_holdings = []

    for field in embed.fields:
        name_field = field.name
        value_field = field.value
        embed_split = name_field.split(' ')
        broker_name = embed_split[0]

        group_number = embed_split[1] if len(embed_split) > 1 else '1'
        account_number_match = re.search(r'xxxx([\dA-Z]+)', name_field)

        account_number = account_number_match.group(1) if account_number_match else None

        if not account_number:
            continue

        if account_number.isdigit():
            account_number = account_number.zfill(4)

        account_nickname = get_account_nickname_or_default(broker_name, group_number, account_number)
        account_key = f"{broker_name} {account_nickname}"

        new_holdings = []
        account_total = None
        for line in value_field.splitlines():
            if "No holdings in Account" in line:
                continue
            match = re.match(r"([\w\s]+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line)
            if match:
                stock = match.group(1).strip()
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append([account_key, broker_name, group_number, account_number, stock, quantity, price, total_value])

            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

        if account_total:
            for holding in new_holdings:
                holding.append(account_total)

        parsed_holdings.extend(new_holdings)

    return parsed_holdings

def parse_fennel_message(embed):
    """
    Parses an embed message and returns parsed holdings data for Fennel accounts.
    """
    parsed_holdings = []

    for field in embed.fields:
        name_field = field.name
        value_field = field.value
        embed_split = name_field.split(' ')
        broker_name = embed_split[0]  # Keep broker_name as-is (no normalization)
        group_number = embed_split[1] if len(embed_split) > 1 else '1'

        # Correct capitalization for specific brokers
        if broker_name.upper() == 'WELLSFARGO':
            broker_name = 'Wellsfargo'
        elif broker_name.upper() == 'VANGUARD':
            broker_name = 'Vanguard'

        # Extract account number
        account_number_match = re.search(r'\(Account (\d+)\)', name_field)
        account_number = account_number_match.group(1) if account_number_match else None

        if not account_number:
            continue

        # Get account nickname, or return account number if no mapping found
        try:
            account_nickname = get_account_nickname(broker_name, group_number, account_number)
        except KeyError:
            account_nickname = "AccountNotMapped"

        # Construct account key
        account_key = f"{broker_name} {account_nickname}"

        new_holdings = []
        account_total = None

        for line in value_field.splitlines():
            if "No holdings in Account" in line:
                continue
            match = re.match(r"([\w\s]+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line)
            if match:
                stock = match.group(1).strip()
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append([account_key, broker_name, group_number, account_number, stock, quantity, price, total_value])

            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

        if account_total:
            for holding in new_holdings:
                holding.append(account_total)

        parsed_holdings.extend(new_holdings)

    return parsed_holdings


def get_account_nickname_or_default(broker_name, group_number, account_number):
    """
    Returns the account nickname if found, otherwise returns 'AccountNotMapped'.
    """
    try:
        # Assuming get_account_nickname is the existing function to retrieve the account nickname
        return get_account_nickname(broker_name, group_number, account_number)
    except KeyError:
        # If the account is not found, return 'AccountNotMapped'
        return 'AccountNotMapped'

