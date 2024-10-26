import csv
import json
import logging
import re
from datetime import datetime

from discord import embeds

from utils.config_utils import (get_account_nickname, load_account_mappings,
                                load_config)
from utils.csv_utils import (get_holdings_for_summary, read_holdings_log,
                             save_holdings_to_csv, save_order_to_csv)
from utils.watch_utils import update_watchlist

# Load configuration
config = load_config()
ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']

# Order headers
ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Key', 'Broker Name', 'Broker Number', 'Account', 'Stock', 'Quantity', 'Price', 'Position Value', 'Account Total']

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
    'robinhood': r'(Robinhood\s\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'fidelity': r'(Fidelity\s\d+)\saccount\s(?:xxxxx)?(\d+):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
    'tradier_verification': r'(Tradier)\saccount\s(?:xxxx)?(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+):\s(ok|failed)',
    'webull_buy': r'(Webull\s\d+):\sbuying\s(\d+\.?\d*)\sof\s(\w+)',
    'wellsfargo': r'(WELLSFARGO\s\d+)\s\*\*\*(\d+):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
    'webull_sell': r'(Webull\s\d+):\ssell\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\w+):\s(Success|Failed)',
    'fennel': r'(Fennel\s\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sAccount\s(\d+):\s(Success|Failed)',
    'public': r'(Public\s\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'schwab_order': r'(Schwab\s\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)',
    'tradier_order': r'(Tradier\s\d+):\s(buying|selling)\s(\d+\.?\d*)\sof\s(\w+)',
    'chase_order': r'(Chase\s\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(LIMIT|MARKET)',
    'schwab_verification': r'(Schwab\s\d+)\saccount\s(?:xxxx)?(\d+):\sThe order verification was successful',
    'schwab_failure': r"Schwab\s\d+\saccount\s(\w+):\sThe order verification produced the following messages:",
    'chase_verification': r'(Chase\s\d+)\saccount\s(?:xxxx)?(\d+):\sThe order verification was successful',
    'firstrade_order': r"(Firstrade\s\d+)\s(buying|selling)\s(\d+\.?\d*)\s([A-Z]+)\s@\s(market|limit)",
    'firstrade_verification': r"(Firstrade\s\d+)\saccount\sxxxx(\d{4}):\sThe order verification was\s(successful|unsuccessful)",
    'firstrade_failure': r"Firstrade\s\d+\saccount\s(\w+):\sThe order verification produced the following messages:",
    'bbae': r'(?i)(BBAE\s\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)'
}


def parse_order_message(content):
    """Parses an order message and extracts relevant details based on broker formats."""
    for broker, pattern in patterns.items():
        match = re.match(pattern, content)
        if match:
            # Split the broker into broker_name and broker_number if applicable
            broker_split = match.group(0).split()  # Use the first matched group (broker) to split
            broker_name = broker_split[0]  # Extract broker name (e.g., 'Fidelity')
            broker_number = broker_split[1] if len(broker_split) > 1 else "N/A"  # Extract broker number or set as "N/A"
            print(f'Matching {broker_name} broker number {broker_number} to mapped accounts.')

            if broker in ['schwab_order', 'chase_order', 'firstrade_order', 'tradier_order']:
                print(f"Processing incomplete order for {broker_name} {broker_number}")
                handle_incomplete_order(match, broker_name, broker_number)
            elif broker in ['schwab_verification', 'chase_verification', 'firstrade_verification', 'tradier_verification']:
                print(f"Received verification message for {broker_name} broker number {broker_number}")
                handle_verification(match, broker_name, broker_number)
            elif broker in ['schwab_failure', 'firstrade_failure']:
                print("Received failure message, removing failed account...")
                handle_failed_order(match, broker_name, broker_number)
            else:
                # For complete orders, pass broker_name and broker_number to handle_complete_order
                handle_complete_order(match, broker_name, broker_number)
            return
    print(f"Failed to parse order message: {content}")
        

def handle_incomplete_order(match, broker_name, broker_number):
    """Handles incomplete buy/sell orders for Chase, Schwab, Tradier, and Firstrade."""
    print(f"Initialized verification for {broker_name} broker number: {broker_number}")
    try:
        # Print matched groups for debugging
        print(f"Matched groups for {broker_name} {broker_number}: {match.groups()[0:4]}")

        # Get other values from match groups
        action, quantity, stock = match.groups()[1:4]
        print(f"Temporary orders for all accounts in {broker_name} {broker_number}, details: {action} {quantity} {stock}")

        # Ensure none of the variables are missing
        if not action or not quantity or not stock:
            raise ValueError(f"Missing values: action={action}, quantity={quantity}, stock={stock}")

        # Load the account mapping
        account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)

        # Check if the broker exists in the mapping
        if broker_name in account_mapping:
            broker_level_names = account_mapping[broker_name]

            # Check if the group number (broker_number) exists in the broker's accounts
            if broker_number in broker_level_names:
                account_level_numbers = broker_level_names[broker_number]

                # Iterate through accounts in the group
                for account_number, nickname in account_level_numbers.items():
                    print(f"Generating temporary order for {nickname} - last four: {account_number}.")

                    # Populate incomplete_orders with broker_name, broker_number, action, quantity, and stock
                    incomplete_orders[(stock, account_number)] = {
                        'broker_name': broker_name,
                        'broker_number': broker_number,
                        'account_number': account_number,
                        'nickname': nickname,
                        'action': action,
                        'quantity': quantity,
                        'stock': stock
                    }
                    print(f"Saved placeholder order for account {account_number} ({nickname}): {incomplete_orders[(stock, account_number)]}")
            else:
                print(f"Group number {broker_number} not found for broker {broker_name}.")
        else:
            print(f"Broker {broker_name} not found in account mapping.")

    except ValueError as e:
        print(f"Error in handle_incomplete_order: {e}")


def handle_verification(match, broker_name, broker_number):
    """Processes order verification for Chase, Schwab, and Firstrade."""
    print(f"Verification order passed for {broker_name} {broker_number}")
    
    # Load the account mapping
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
    
    # Extract the account number from the matched groups
    account_number = match.groups()[1]
    
    # Check if the broker exists in the mapping
    if broker_name in account_mapping:
        broker_accounts = account_mapping[broker_name]
        
        # Check if the group number (broker_number) exists in the broker's accounts
        if broker_number in broker_accounts:
            temp_orders_account_level = broker_accounts[broker_number]
            
            # Check if the account number is in the group
            if account_number in temp_orders_account_level:
                print(f"Account {account_number} found for {broker_name} {broker_number}. Processing verification.")
                # Call process_verified_orders with the relevant accounts
                process_verified_orders(broker_name, account_number, temp_orders_account_level)
            else:
                print(f"Account {account_number} not found for {broker_name} {broker_number}.")
        else:
            print(f"Group number {broker_number} not found for broker {broker_name}.")
    else:
        print(f"Broker {broker_name} not found in account mapping.")


def process_verified_orders(broker_name, account_number, temp_orders_account_level):
    """Processes verified orders for the specified broker."""
    print(f"Processing verified orders for {broker_name}, account number: {account_number}")
    
    # Ensure that account_list contains valid account data
    if not temp_orders_account_level:
        print(f"No placeholder orders found for broker {broker_name}.")
        return
    
    # Iterate through incomplete orders to find matching stock and account
    for (stock, account), order in list(incomplete_orders.items()):
        # Check if the broker name, account number, and action match the placeholder order
        if order['broker_name'] == broker_name and order['account_number'] == account_number:
            # Account has been found; remove the verified order from the incomplete list
            del incomplete_orders[(stock, account)]

            # Retrieve broker_number from the order data
            broker_number = order.get('broker_number')

            # Save the verified order to CSV using the provided broker_name, broker_number, account_number, etc.
            save_order_to_csv(broker_name, broker_number, account_number, order['action'], order['quantity'], stock)

            # Log the successful processing of the verified order
            print(f"Verified order {order['action']} {order['quantity']} of {stock} for {broker_name} {broker_number}, Account: {account_number}")
            break
        else:
            print(f"Order for {broker_name} {account_number} not found in incomplete orders.")


def handle_complete_order(match, broker_name, broker_number):
    """Handles complete buy and sell orders."""
    try:
        # Initialize variables with default values
        account_number = None
        action = None
        quantity = None
        stock = None

        print(f"Processing order for broker: {broker_name} {broker_number}, match: {match.groups()}")

        # Extract data from the match groups based on the broker
        if broker_name.lower() in ['robinhood', 'public', 'bbae', 'fennel']:
            # Specific to these brokers
            action, quantity, stock, account_number = match.groups()[1:5]
        elif broker_name.lower() == 'webull':
            # Webull-specific sell
            if 'sell' in match.group(0).lower():
                # Webull-specific sell
                quantity, stock, account_number = match.groups()[1:4]
                action = 'sell'
            elif 'buy' in match.group(0).lower():
                # Webull-specific buy
                quantity, stock = match.groups()[1:3]
                account_number = 'N/A'
                action = 'buy'
        elif broker_name.lower() in ['fidelity', 'wellsfargo']:
            # Fidelity/Wells Fargo extract account and action
            account_number, action, quantity, stock = match.groups()[1:5]
        else:
            raise ValueError(f"Broker {broker_name} not recognized in complete order handler.")

        # If it's a sell order, mark it as pending closure
        if action == 'sell':
            update_watchlist(broker_name, account_number, stock, 0, order_type='sell')  # Use quantity=0 for pending closure

        # Save the order with the broker and broker_number
        save_order_to_csv(broker_name, broker_number, account_number, action, quantity, stock)
        print(f"{broker_name} {broker_number}, Account {account_number}, {action.capitalize()} {quantity} of {stock}")

    except Exception as e:
        print(f"Error handling complete order: {e}")


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


def parse_manual_order_message(content):
    """Parses a manual order message. Expected format: 'manual Broker BrokerNumber Account OrderType Stock Price'"""
    try:
        parts = content.split()
        if len(parts) != 7:
            raise ValueError("Invalid format. Expected 'manual Broker BrokerNumber Account OrderType Stock Price'.")

        return {
            'broker_name': parts[1],
            'group_number': parts[2],  # Broker Number
            'account': parts[3],      # Account
            'order_type': parts[4],   # Order type (buy/sell)
            'stock': parts[5],        # Stock ticker symbol
            'price': float(parts[6])  # Price
        }
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

        
def parse_manual_order_message(content):
    """Parses a manual order message. Expected format: 'manual Broker BrokerNumber Account OrderType Stock Price'"""
    try:
        parts = content.split()
        for part in parts:
            print(f"Part: {part}")
        
        # Expected format length check (7 parts now: manual, broker, broker_number, account, order_type, stock, price)
        if len(parts) != 7:
            raise ValueError("Invalid format. Expected 'manual Broker BrokerNumber Account OrderType Stock Price'.")

        # Returning the parsed values
        return {
            'broker_name': parts[1],
            'group_number': parts[2],  # Combining Broker and BrokerNumber
            'account': parts[3],      # Account
            'order_type': parts[4],   # Order type (e.g., 'buy' or 'sell')
            'stock': parts[5],        # Stock ticker symbol
            'price': float(parts[6])  # Price converted to float
        }
    except Exception as e:
        print(f"Error parsing manual order: {e}")
        return None


def parse_embed_message(embed, holdings_log_file):
    """
    Parses an embed message and updates holdings in the CSV log based on the new JSON structure.
    """
    for field in embed.fields:
        name_field = field.name
        embed_split = name_field.split(' ')
        broker_name = embed_split[0]  # Extract broker name
        group_number = embed_split[1] if len(embed_split) > 1 else '1'  # Extract group number or default to '1'
        print(broker_name, group_number,)

        # Extract the account number (only the last 4 digits, skipping the 'xxxxx' part)
        account_number_match = re.search(r'x+(\d+)', field.name)  # Match the visible part of the account number
        account_number = account_number_match.group(1) if account_number_match else None
        print(account_number)

        # If there's no account number, skip this field
        if not account_number:
            continue

        # Get the account nickname using the helper function with broker, group number, and account number
        account_nickname = get_account_nickname(broker_name, group_number, account_number)
        mapped_account = f"{broker_name} {account_nickname}"
        account_key = mapped_account

        print(f"Broker: {broker_name}, Account Number: {account_number}, Group Number: {group_number}")
        print(f"Account Nickname: {account_nickname}")

        # Read existing holdings log
        existing_holdings = []
        with open(holdings_log_file, 'r') as file:
            csv_reader = csv.reader(file)
            existing_holdings = [row for row in csv_reader if row[0] != account_key]

        # Parse the new holdings from the message
        new_holdings = []
        account_total = None
        for line in field.value.splitlines():
            # Check for "No holdings in Account" and skip it
            if "No holdings in Account" in line:
                continue

            # Example of line: "CTNT: 1.0 @ $0.19 = $0.19"
            match = re.match(r"(\w+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line)
            if match:
                stock = match.group(1)
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append([account_key, broker_name, group_number, account_number, stock, quantity, price, total_value])
          
            # Extract the total value for the account
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
