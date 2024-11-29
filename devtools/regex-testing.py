# -- Put me in rsassistant/src/.


import re
import logging
from datetime import datetime

from utils.config_utils import load_account_mappings
from utils.parsing_utils import normalize_order_data, get_last_stock_price, parse_broker_data

ACCOUNT_MAPPING_FILE = "config/account_mapping.json"
incomplete_orders = {}

# Patterns for confirm messages
order_patterns = {
    'complete': {
        'BBAE': r'(BBAE)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)',
        'Fennel': r'(Fennel)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sAccount\s(\d+):\s(Success|Failed)',
        'Public': r'(Public)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)',
        'Robinhood': r'(Robinhood)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)',
        'WELLSFARGO': r'(WELLSFARGO)\s(\d+)\s\*\*\*(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
        'Fidelity': r'(Fidelity)\s(\d+)\saccount\s(?:xxxxx|xxxx)?(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
        'DSPAC': r'(DSPAC)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)'
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
        'Tradier': r'(Tradier)\saccount\sxxxx(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+):\s(ok|failed)',
        'Webull': r'(Webull)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sxxxx(\w+):\s(Success|Failed)'
    }
}

# def normalize_order_data(broker_name, broker_number, action, quantity, stock, account_number):
#     """Ensures consistent formatting of order data."""
#     # Capitalize broker name properly, except for 'BBAE'
#     if broker_name != 'BBAE':
#         broker_name = broker_name.capitalize()

#     # Standardize action to 'buy' or 'sell'
#     if action.lower() == 'buying':
#         action = 'buy'
#     elif action.lower() == 'selling':
#         action = 'sell'
#     else:
#         action = action.lower()

#     # Ensure broker number is an integer and quantity is a float
#     broker_number = int(broker_number)
#     quantity = float(quantity)

#     # Pad account number to 4 digits with leading zeros if needed
#     account_number = str(account_number).zfill(4)

#     return broker_name, broker_number, action, quantity, stock, account_number

def handle_complete_order(match, broker_name, broker_number):
    """Processes complete buy/sell orders after normalization and saves to CSV and database."""
    try:
        # Parse broker-specific data
        account_number, action, quantity, stock = parse_broker_data(
            broker_name, match, "complete"
        )
        if not account_number or not action or not stock:
            logging.error(
                f"Failed to parse broker data for {broker_name}. Skipping order."
            )
            return

        # Normalize data
        broker_name, broker_number, action, quantity, stock, account_number = (
            normalize_order_data(
                broker_name, broker_number, action, quantity, stock, account_number
            )
        )
        logging.info(
            f"Matched order info for {broker_name} {broker_number} {action} {quantity} {stock} {account_number}"
        )

        # Get price and current date
        price = get_last_stock_price(stock)
        date = datetime.now().strftime("%Y-%m-%d")

        # Prepare order data
        order_data = {
            "Broker Name": broker_name,
            "Broker Number": broker_number,
            "Account Number": account_number,
            "Order Type": action.capitalize(),
            "Stock": stock,
            "Quantity": quantity,
            "Price": price,
            "Date": date,
        }

        logging.info(f"Processing complete order for {broker_name} {broker_number} to CSV")
        # Save the order data to CSV
        save_order_to_csv(order_data)

        # Save the order data to the database
        logging.info(f"Passing to database for {broker_name} {account_number}")
        # with get_db_connection() as conn:
        #     cursor = conn.cursor()
        #     account_id = get_account_id(
        #         cursor, broker_name, broker_number, account_number
        #     )
        #     order_data["Account ID"] = account_id
        #     add_order(order_data)
        #     logging.info(f"Order successfully saved to database for stock {stock}")
    except Exception as e:
        logging.error(
            f"Error handling complete order for {broker_name} {broker_number}: {e}",
            exc_info=True,
        )

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
        account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
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
        account_number = match.group(3)
        action = match.group(4).lower() if 'Tradier' in broker_name else None

        # Normalize data
        broker_name, broker_number, action, _, _, account_number = normalize_order_data(
            broker_name, broker_number, action, 0, '', account_number
        )

        print(f"Verification received for {broker_name} {broker_number}, Account {account_number}")

        for key, order in list(incomplete_orders.items()):
            if (order['broker_name'] == broker_name and
                order['broker_number'] == broker_number and
                order['account_number'] == account_number and
                (action is None or order['action'] == action)):

                process_verified_orders(broker_name, account_number, order)
                del incomplete_orders[key]
                print(f"Verified and removed temporary order for Account {account_number}")
                break
        else:
            print(f"No matching temporary order found for {broker_name} {broker_number}, Account {account_number}")

    except Exception as e:
        print(f"Error in handle_verification: {e}")

def process_verified_orders(broker_name, account_number, order):
    """Processes and finalizes a verified order."""
    print(f"Verified order processed for {broker_name}, Account {account_number}:")
    print(f"Action: {order['action'].capitalize()}, Quantity: {order['quantity']}, Stock: {order['stock']}")
    print("Order has been finalized and logged.")

def parse_order_message(content):
    """Parses incoming messages and routes them to the correct handler based on type."""
    for order_type, patterns in order_patterns.items():
        for broker, pattern in patterns.items():
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

# Example save_order_to_csv function
def save_order_to_csv(order):
    """Appends an order to a CSV file."""
    import csv
    fieldnames = ['broker_name', 'broker_number', 'account_number', 'action', 'quantity', 'stock']
    with open('test_orders.csv', mode='a', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writerow(order)

# Interactive mode to test the function
print("Enter a message to parse (or type 'exit' to quit):")
while True:
    user_input = input("Message: ")
    if user_input.lower() == "exit":
        print("Exiting the parser.")
        break
    parse_order_message(user_input)
    print("-" * 40)
