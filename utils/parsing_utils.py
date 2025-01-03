import csv
import json
import logging
import re
from typing import Optional, Tuple, Match
from datetime import datetime
from logging.handlers import RotatingFileHandler

from discord import embeds

# from RSAssistant import send_discord_alert
from utils.utility_utils import get_last_stock_price
from utils.csv_utils import save_holdings_to_csv, save_order_to_csv
from utils.config_utils import (
    get_account_nickname,
    ACCOUNT_MAPPING,
    DISCORD_PRIMARY_CHANNEL
)
from utils.sql_utils import (
    get_db_connection,
    get_account_id,
    add_order,
    insert_holdings
    )

account_mapping = ACCOUNT_MAPPING

# Store incomplete orders
incomplete_orders = {}

order_patterns = {
    "complete": {
        "BBAE": r"(BBAE)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)",
        "Fennel": r"(Fennel)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sAccount\s(\d+):\s(Success|Failed)",
        "Public": r"(Public)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)",
        "Robinhood" : r"(Robinhood)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)",
        "WELLSFARGO": r"(WELLSFARGO)\s(\d+)\s\*\*\*(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)",
        "Fidelity": r"(Fidelity)\s(\d+)\saccount\s(?:xxxxx)?(\d{4}):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)",
        "Webull": r"(Webull)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxx|xxxx)?(\w+):\s(Success|Failed)",
        "DSPAC": r"(DSPAC)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d{4}):\s(Success|Failed)",
        "Plynk": r"(Plynk)\s(\d+)\sAccount\s(?P<account_number>\d{4})\s(?P<action>buy|sell)\s(?P<stock>\w+)",
    },
    "incomplete": {
        "Schwab": r"(Schwab)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)",
        "Firstrade": r"(Firstrade)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)",
        "Vanguard": r"(Vanguard)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)",
        "Chase": r"(Chase)\s(\d+)\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(LIMIT|MARKET)",
        "Tradier": r"(Tradier)\s(\d+):\s(buying|selling)\s(\d+\.?\d*)\sof\s([A-Z]+)",
    },
    "verification": {
        "Schwab": r"(Schwab)\s(\d+)\saccount\sxxxx(\d{4}):\sThe\sorder\sverification\swas\ssuccessful",
        "Firstrade": r"(Firstrade)\s(\d+)\saccount\sxxxx(\d{4}):\sThe\sorder\sverification\swas\ssuccessful",
        "Vanguard": r"(Vanguard)\s(\d+)\saccount\sxxxx(\d{4}):\sThe\sorder\sverification\swas\ssuccessful",
        "Chase": r"(Chase)\s(\d+)\saccount\s(\d{4}):\sThe\sorder\sverification\swas\ssuccessful",
        "Tradier": r"Tradier account xxxx(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+):\s(ok|failed)",
        "Webull": r"(Webull)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxx|xxxx)?(\w+):\s(Success|Failed)",
    },
}

# Chapt Complete Orders Main
def parse_order_message(content):
    """Parses incoming messages and routes them to the correct handler based on type."""
    for order_type, patterns in order_patterns.items():
        for broker_name, pattern in patterns.items():
            match = re.match(pattern, content, re.IGNORECASE)
            if match:
                broker_name = match.group(1)
                broker_number = match.group(2)

                # Route to the correct handler based on the type
                if order_type == "complete":
                    handle_complete_order(match, broker_name, broker_number)
                elif order_type == "incomplete":
                    handle_incomplete_order(match, broker_name, broker_number)
                elif order_type == "verification":
                    handle_verification(match, broker_name, broker_number)
                return  # Exit once a match is found

    logging.error(f"No match found for message: {content}")

def parse_broker_data(
    broker_name: str, match: Optional[Match], order_type: str
) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[str]]:
    """
    Parses broker-specific data based on regex match and field positions.

    Args:
        broker_name (str): Name of the broker (case insensitive).
        match (Optional[Match]): The regex match object from parsing the order.
        order_type (str): The type of order ('complete', 'incomplete', or 'verification').

    Returns:
        Tuple[Optional[str], Optional[str], Optional[float], Optional[str]]:
        - account_number: The account number or None if not applicable.
        - action: The action performed (e.g., 'buy', 'sell') or None.
        - quantity: The quantity of stock as a float or None.
        - stock: The stock symbol or None.

    Raises:
        Logs errors if the broker or order type is unsupported or if field extraction fails.
    """
    field_positions = {
        "complete": {
            "BBAE": (6, 3, 4, 5),
            "Fennel": (6, 3, 4, 5),
            "Public": (6, 3, 4, 5),
            "Robinhood": (6, 3, 4, 5),
            "WELLSFARGO": (3, 4, 5, 6),
            "Fidelity": (3, 4, 5, 6),
            "Webull": (6, 3, 4, 5),
            "DSPAC": (6, 3, 4, 5),
            "Plynk": ("account_number", "action", None, "stock"),
        },
        "incomplete": {
            "Schwab": (None, 3, 4, 5),
            "Firstrade": (None, 3, 4, 5),
            "Vanguard": (None, 3, 4, 5),
            "Chase": (None, 3, 4, 5),
            "Tradier": (None, 3, 4, 5),
        },
        "verification": {
            "Schwab": (3, None, None, None),
            "Firstrade": (3, None, None, None),
            "Vanguard": (3, None, None, None),
            "Chase": (3, None, None, None),
            "Tradier": (1, 2, 3, 4),
            "Webull": (3, 4, None, 5),
        },
    }

    # Ensure broker name is normalized for lookup
    broker_key = broker_name
    if broker_name in (['BBAE'], ['DSPAC']):
        broker_key = broker_name.upper()
        
    positions = field_positions.get(order_type, {}).get(broker_key)

    if not positions:
        logging.error(
            f"No field mapping defined for broker: {broker_name} ({broker_key}), order_type: {order_type}"
        )
        return None, None, None, None

    if not match:
        logging.error(f"Regex match object is None for broker: {broker_name}, order_type: {order_type}")
        return None, None, None, None

    # Extract fields using positions
    try:
        account_number = match.group(positions[0]) if positions[0] else None
        action = match.group(positions[1]) if positions[1] else None
        quantity = float(match.group(positions[2])) if positions[2] else None
        stock = match.group(positions[3]) if positions[3] else None

        return account_number, action, quantity, stock
    except IndexError as e:
        logging.error(
            f"Field extraction failed for broker: {broker_name}, order_type: {order_type}, error: {e}"
        )
        return None, None, None, None

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
                broker_name, broker_number, action, quantity, stock, account_number))

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

        logging.info(f"Processing complete order for {broker_name} {broker_number} to CSV and database")
        # Save the order data to CSV
        handoff_order_data(order_data, broker_name, broker_number, account_number)

        logging.info(
            f"Normalized function handled for: {broker_name} {broker_number} {action} {quantity} {stock} {account_number}"
        )

    except Exception as e:
        logging.error(
            f"Error handling complete order for {broker_name} {broker_number}: {e}",
            exc_info=True,
        )

def normalize_order_data(
    broker_name, broker_number, action, quantity, stock, account_number
):
    """
    Normalize order data for consistent formatting and apply broker-specific adjustments.
    
    Args:
        broker_name (str): Name of the broker.
        broker_number (int or str): Broker identifier number.
        action (str): Action performed ('buy', 'sell', or variations like 'buying', 'selling').
        quantity (float): Quantity of stock involved in the transaction.
        stock (str): Stock symbol (e.g., 'AAPL').
        account_number (str or int): Account identifier.
    
    Returns:
        tuple: Normalized (broker_name, broker_number, action, quantity, stock, account_number).
    
    Notes:
        - Broker names are capitalized unless listed in exceptions ('BBAE', 'DSPAC').
        - Actions are standardized to 'buy' or 'sell'.
        - Webull-specific 99/999 sell lot adjustment: Changes to 'buy' with quantity 1.0.
        - Account numbers are zero-padded to 4 digits for consistency.
        - Logs Webull-specific adjustments.
        - Sends alert for negative holdings
    """
    # Capitalize broker name, except for specified exceptions
    if broker_name not in {"BBAE", "DSPAC"}:
        broker_name = broker_name.capitalize()

    # Standardize action
    if action:
        action = action.lower()
        if action == "buying":
            action = "buy"
        elif action == "selling":
            action = "sell"

    # Webull-specific adjustment for sell lots of 99.0 or 999.0
    if broker_name.lower() == "webull" and action == "sell" and quantity in {99.0, 999.0}:
        action = "buy"
        quantity = 1.0
        logging.info(
            f"Webull Adjustment: Changed action to 'buy' and quantity to 1.0 for broker {broker_number}, account {account_number}."
        )

    # Ensure account number is a string, zero-padded to 4 digits
    account_number = str(account_number).zfill(4) if account_number is not None else "0000"

    # Ensure broker number is a string
    broker_number = str(broker_number)

    # Validate and normalize quantity to a float
    
    quantity = float(quantity)
    if quantity <= 0:
        logging.warning(f"Negative holdings detected: {quantity} for stock {stock}.")
        # Trigger the Discord alert asynchronously

        send_negative_holdings(quantity, stock, broker_name, broker_number, account_number)
    elif quantity == 0.0:
        quantity = 0.0

    logging.info(
        f"Matched order info for {broker_name} {broker_number} {action} {quantity} {stock} {account_number}"
        )
    
    return broker_name, broker_number, action, quantity, stock, account_number

# Chapt Incomplete, Failed, and Manual Orders
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

        logging.info(
            f"Initializing temporary order for {broker_name} {broker_number}: {action} {quantity} of {stock}"
        )

        broker_accounts = account_mapping.get(broker_name, {}).get(str(broker_number))
        if broker_accounts:
            for account, nickname in broker_accounts.items():
                incomplete_orders[(stock, account)] = {
                    "broker_name": broker_name,
                    "broker_number": broker_number,
                    "account_number": account,
                    "nickname": nickname,
                    "action": action,
                    "quantity": quantity,
                    "stock": stock,
                }
                logging.info(
                    f"Temporary order created for {nickname} - Account ending {account}"
                )
        else:
            logging.error(
                f"No accounts found for broker {broker_name} number {broker_number}"
            )

    except Exception as e:
        logging.error(f"Error in handle_incomplete_order: {e}")

def handle_verification(match, broker_name, broker_number):
    quantity = 1  # Set a default value to avoid "referenced before assignment" error
    """Processes order verification and finalizes incomplete orders."""
    try:
        # Initialize variables
        account_number = None
        action = None  # Default action to None

        # Extract fields based on broker type for verification
        if broker_name.lower() in {"schwab", "firstrade", "vanguard", "chase"}:
            account_number = match.group(3) if match and match.lastindex >= 3 else None
            # These brokers do not specify an action in verification messages
            action = None

        elif broker_name.lower() in {"tradier", "webull"}:
            account_number = match.group(3) if match and match.lastindex >= 3 else None
            action = match.group(4).lower() if match and match.lastindex >= 4 else None

        else:
            raise ValueError(f"Unknown broker format for verification: {broker_name}")

        # Ensure account_number is valid
        if not account_number:
            raise ValueError(f"Missing account number in verification for {broker_name}")

        # Normalize data
        broker_name, broker_number, action, _, _, account_number = normalize_order_data(
            broker_name, broker_number, action, 1, "", account_number
        )

        logging.info(
            f"Verification received for {broker_name} {broker_number}, Account {account_number}"
        )

        # Check for matching incomplete orders and finalize them upon verification
        for key, order in list(incomplete_orders.items()):
            # Log order comparison details for debugging
            logging.debug(
                f"Comparing: order_action={order['action']}, verification_action={action}"
            )

            # Safely handle None values for action
            if (
                order["broker_name"] == broker_name
                and order["broker_number"] == broker_number
                and order["account_number"] == account_number
                and (action is None or order["action"] == action)
            ):
                # Merge details from incomplete order
                order["action"] = order.get("action") or action
                order["quantity"] = order.get("quantity") or 1  # Default to 1 if missing
                process_verified_orders(broker_name, broker_number, account_number, order)
                order["quantity"] = order.get("quantity", 1)  # Default quantity if missing
                del incomplete_orders[key]
                logging.info(
                    f"Verified and removed temporary order for Account {account_number}"
                )
                break
        else:
            logging.error(
                f"No matching temporary order found for {broker_name} {broker_number}, Account {account_number}"
            )

    except ValueError as ve:
        logging.error(
            f"ValueError in handle_verification: {ve}. Broker: {broker_name}, Match: {match}"
        )
    except AttributeError as ae:
        logging.error(
            f"AttributeError in handle_verification: {ae}. Match details: {match}"
        )
    except Exception as e:
        logging.error(f"Unexpected error in handle_verification: {e}")

def process_verified_orders(broker_name, broker_number, account_number, order):
    order["quantity"] = order.get("quantity", 1)  # Default quantity if missing
    """Processes and finalizes a verified order by passing it to handle_complete_order."""
    logging.info(
        f"Verified order processed for {broker_name} {broker_number}, Account {account_number}:"
    )
    action = order["action"]
    quantity = order["quantity"]
    stock = order["stock"]

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

    logging.info(f"Processing complete order for {broker_name} {broker_number} to CSV and database.")
    # Save the order data to CSV
    handoff_order_data(order_data, broker_name, broker_number, account_number)

def handle_failed_order(match, broker_name, broker_number):
    """Handles failed orders by removing incomplete entries."""
    try:
        account_number = match.group(1)
        to_remove = [
            (stock, account)
            for (stock, account), order in incomplete_orders.items()
            if order["broker"] == broker_name and account == account_number
        ]

        for item in to_remove:
            del incomplete_orders[item]
            logging.info(f"Removed failed order for {broker_name} {account_number}")

    except Exception as e:
        logging.error(f"Error handling failed order: {e}")

def handoff_order_data(order_data, broker_name, broker_number, account_number):
    logging.info(f"Processed order data, passing to logs and database.")
    # Save the order data to CSV
    save_order_to_csv(order_data)
    logging.info(f"Order successfully saved to CSV for stock {order_data['Stock']}")
    # Save the order data to the database

    logging.info(f"Passing to database for {broker_name} {account_number}")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        account_id = get_account_id(
            cursor, broker_name, broker_number, account_number
        )
        order_data["Account ID"] = account_id
        add_order(order_data)
    logging.info(f"Completed order processing loop for {broker_name} {account_number}")

# Chapt Parse Holdings
def parse_embed_message(embed):
    """
    Handles a new holdings message by parsing it and saving the holdings to CSV.
    """
    # Step 1: Parse the holdings from the embed message
    parsed_holdings = main_embed_message(embed)
    # Step 2: Save the parsed holdings to CSV
    save_holdings_to_csv(parsed_holdings)
    insert_holdings(parsed_holdings)

    logging.info("Holdings have been successfully parsed and saved.")

def main_embed_message(embed):
    """
    Parses an embed message based on the broker name.
    Dispatches to specific handler functions or general handler based on broker.
    Returns parsed holdings data.
    """
    broker_name = embed.fields[0].name.split(" ")[0]

    if broker_name.lower() == "webull":
        return parse_webull_embed_message(embed)
    elif broker_name.lower() == "fennel":
        return parse_fennel_embed_message(embed)
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
        embed_split = name_field.split(" ")
        broker_name = embed_split[0]

        # Correct capitalization for specific brokers
        if broker_name.upper() == "WELLSFARGO":
            broker_name = "Wellsfargo"
        elif broker_name.upper() == "VANGUARD":
            broker_name = "Vanguard"
        elif broker_name.upper() == "SOFI":
            broker_name == "Sofi"

        group_number = embed_split[1] if len(embed_split) > 1 else "1"
        account_number_match = re.search(r"x+(\d+)", name_field)

        if not account_number_match:
            account_number_match = re.search(r"\((\d+)\)", name_field)

        account_number = account_number_match.group(1) if account_number_match else None

        if not account_number:
            continue

        account_nickname = get_account_nickname_or_default(
            broker_name, group_number, account_number
        )
        account_key = f"{broker_name} {account_nickname}"

        new_holdings = []
        account_total = None
        for line in value_field.splitlines():
            if "No holdings in Account" in line:
                continue
            match = re.match(
                r"([\w\s]+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line
            )
            if match:
                stock = match.group(1).strip()
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append(
                    [
                        account_key,
                        broker_name,
                        group_number,
                        account_number,
                        stock,
                        quantity,
                        price,
                        total_value,
                    ]
                )

            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

        if account_total:
            for holding in new_holdings:
                holding.append(account_total)

        parsed_holdings.extend(new_holdings)
        logging.info(parsed_holdings)

    return parsed_holdings

def parse_webull_embed_message(embed):
    """
    Parses an embed message and returns parsed holdings data for Webull accounts.
    """
    parsed_holdings = []

    for field in embed.fields:
        name_field = field.name
        value_field = field.value
        embed_split = name_field.split(" ")
        broker_name = embed_split[0]

        group_number = embed_split[1] if len(embed_split) > 1 else "1"
        account_number_match = re.search(r"xxxx([\dA-Z]+)", name_field)

        account_number = account_number_match.group(1) if account_number_match else None

        if not account_number:
            continue

        if account_number.isdigit():
            account_number = account_number.zfill(4)

        account_nickname = get_account_nickname_or_default(
            broker_name, group_number, account_number
        )
        account_key = f"{broker_name} {account_nickname}"

        new_holdings = []
        account_total = None
        for line in value_field.splitlines():
            if "No holdings in Account" in line:
                continue
            match = re.match(
                r"([\w\s]+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line
            )
            if match:
                stock = match.group(1).strip()
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append(
                    [
                        account_key,
                        broker_name,
                        group_number,
                        account_number,
                        stock,
                        quantity,
                        price,
                        total_value,
                    ]
                )

            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

        if account_total:
            for holding in new_holdings:
                holding.append(account_total)

        parsed_holdings.extend(new_holdings)

    return parsed_holdings

def parse_fennel_embed_message(embed):
    """
    Parses an embed message and returns parsed holdings data for Fennel accounts.
    """
    parsed_holdings = []
    try:
        # Loop through embed fields to process each account
        for field in embed.fields:
            name_field = field.name
            value_field = field.value

            # Extract broker, group number, and account details
            embed_split = name_field.split(" ")
            broker_name = embed_split[0]
            group_number = embed_split[1] if len(embed_split) > 1 else "1"

            # Extract account number from parentheses
            account_number_match = re.search(r"\(Account (\d+)\)", name_field)
            account_number = (
                account_number_match.group(1).zfill(4) if account_number_match else None
            )

            if not account_number:
                logging.error(f"Unable to extract account number from: {name_field}")
                continue

            # Create account key
            account_nickname = (
                f"{broker_name} {group_number} (Account {account_number})"
            )
            account_key = f"{broker_name} {account_nickname}"

            # Parse holdings in value_field
            new_holdings = []
            account_total = None

            for line in value_field.splitlines():
                if "No holdings in Account" in line:
                    continue
                match = re.match(
                    r"([\w\s]+): ([\-\d\.]+) @ \$(\d+\.\d+) = \$(\-?\d+\.\d+)", line
                )
                if match:
                    stock = match.group(1).strip()
                    quantity = match.group(2)
                    price = match.group(3)
                    total_value = match.group(4)
                    new_holdings.append(
                        [
                            account_key,
                            broker_name,
                            group_number,
                            account_number,
                            stock,
                            quantity,
                            price,
                            total_value,
                        ]
                    )

                if "Total:" in line:
                    account_total = line.split(": $")[1].strip()

            if account_total:
                for holding in new_holdings:
                    holding.append(account_total)

            parsed_holdings.extend(new_holdings)

        logging.info(f"Parsed Fennel holdings: {parsed_holdings}")
        return parsed_holdings

    except Exception as e:
        logging.error(f"Error parsing Fennel embed message: {e}")
        return []

def get_account_nickname_or_default(broker_name, group_number, account_number):
    """
    Returns the account nickname if found, otherwise returns 'AccountNotMapped'.
    """
    try:
        # Assuming get_account_nickname is the existing function to retrieve the account nickname
        logging.info(f"Getting account nickname for {broker_name} {group_number} {account_number}")
        return get_account_nickname(broker_name, group_number, account_number)
    except KeyError:
        # If the account is not found, return 'AccountNotMapped'
        return "Unmapped Account"

# Chapt Alerts Message Logic
async def send_negative_holdings(DISCORD_SECONDARY_CHANNEL, quantity, stock, broker_name, broker_number, account_number):
    """
    Sends a negative holdings alert to a Discord channel.

    Args:
        channel_id (int): The ID of the target Discord channel.
        quantity (float): The negative quantity detected.
        stock (str): The stock symbol.
        broker_name (str): The name of the broker.
        broker_number (str): The broker identifier.
        account_number (str): The account number associated with the holdings.
    """
    try:
        # Fetch the target channel
        channel = (DISCORD_SECONDARY_CHANNEL)
        if not channel:
            logging.error(f"Channel ID {DISCORD_SECONDARY_CHANNEL} not found. Cannot send alert.")
            return

        # Create the alert embed
        embed = embed(
            title="Negative Holdings Alert",
            description="A negative holdings quantity was detected.",
            color=0xFF0000,
        )
        embed.add_field(name="Stock", value=stock, inline=True)
        embed.add_field(name="Quantity", value=quantity, inline=True)
        embed.add_field(name="Broker Name", value=broker_name, inline=True)
        embed.add_field(name="Broker Number", value=broker_number, inline=True)
        embed.add_field(name="Account Number", value=account_number, inline=True)

        # Send the alert to the channel
        await channel.send(embed=embed)
        logging.info(f"Negative holdings alert sent for stock {stock}, account {account_number}.")

    except Exception as e:
        logging.error(f"Error sending Discord alert for stock {stock}, account {account_number}: {e}")

def alert_channel_message(content):
    """
    Parses alert content and returns a formatted alert message if a match is found.
    
    Args:
        content (str): The content of the message to parse.
        
    Returns:
        str: A formatted alert message or None if no match is found.
    """
    # Updated regex to handle extra spaces or blank lines
    alert_pattern = r"📰 \| (.+?) \((\w+)\)\s*(https?://[^\s]+)"
    match = re.search(alert_pattern, content)

    if match:
        title = match.group(1)  # Extract the full title
        ticker = match.group(2)  # Extract the stock ticker
        url = match.group(3)  # Extract the URL

        # Detect "Reverse Stock Split" in the title
        if "Reverse Stock Split" in title:
            action = "Reverse Stock Split"
        else:
            action = "Corporate Action"

        # Format the alert message
        alert_message = (
            f"🚨 Nasdaq Corporate Actions Alert:\n"
            f"**{ticker} {action}**\n"
            f"[Details Here]({url})"
        )
        return alert_message

    logging.warning("No match found in content for alert message. Content may not follow the expected pattern.")
    return None  # Return None if no match is found
