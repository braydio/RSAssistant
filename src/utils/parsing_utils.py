import csv
import json
import logging
import re
from typing import Optional, Tuple, Match
from datetime import datetime
from logging.handlers import RotatingFileHandler

from discord import embeds

from utils.utility_utils import get_last_stock_price
from utils.csv_utils import save_holdings_to_csv, save_order_to_csv
from utils.init import (
    load_config,
    get_account_nickname,
    load_account_mappings
)

from utils.sql_utils import (
    get_db_connection,
    get_account_id,
    add_order,
    insert_holdings
    )

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
    try:
        quantity = float(quantity)
        if quantity <= 0:
            logging.warning(f"Quantity is non-positive ({quantity}) for stock {stock}.")
    except (TypeError, ValueError):
        logging.error(f"Invalid quantity '{quantity}' provided for stock {stock}.")
        quantity = 0.0

    # Optional: Handle test orders (example behavior)
    if broker_number == "0":
        process_test_order(broker_name, broker_number, action, quantity, stock, account_number)

    return broker_name, broker_number, action, quantity, stock, account_number

def process_test_order(broker_name, broker_number, action, quantity, stock, account_number):
    logging.info(f"Test order registered for {broker_name} {broker_number} {account_number}")

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
        with get_db_connection() as conn:
            cursor = conn.cursor()
            account_id = get_account_id(
                cursor, broker_name, broker_number, account_number
            )
            order_data["Account ID"] = account_id
            add_order(order_data)
            logging.info(f"Order successfully saved to database for stock {stock}")
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

        logging.info(
            f"Initializing temporary order for {broker_name} {broker_number}: {action} {quantity} of {stock}"
        )
        account_mapping = load_account_mappings()
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
    """Processes order verification and finalizes incomplete orders."""
    try:
        # Extract fields based on broker type for verification
        if broker_name.lower() == "schwab":
            account_number = match.group(3)
            action = None  # Action is not specified in Schwab verification messages

        elif broker_name.lower() == "firstrade":
            account_number = match.group(3)
            action = None  # Action is not specified in Firstrade verification messages

        elif broker_name.lower() == "vanguard":
            account_number = match.group(3)
            action = None  # Action is not specified in Vanguard verification messages

        elif broker_name.lower() == "chase":
            account_number = match.group(3)
            action = None  # Action is not specified in Chase verification messages

        elif broker_name.lower() == "tradier":
            account_number = match.group(3)
            action = match.group(
                4
            ).lower()  # Action (buy/sell) is specified in Tradier messages

        elif broker_name.lower() == "webull":
            account_number = match.group(3)
            action = match.group(
                4
            ).lower()  # Action (buy/sell) is specified in Webull messages

        else:
            logging.error(f"Unknown broker format for verification: {broker_name}")
            return

        # Normalize data
        broker_name, broker_number, action, _, _, account_number = normalize_order_data(
            broker_name, broker_number, action, 1, "", account_number
        )

        logging.info(
            f"Verification received for {broker_name} {broker_number}, Account {account_number}"
        )

        # Check for matching incomplete orders and finalize them upon verification
        for key, order in list(incomplete_orders.items()):
            if (
                order["broker_name"] == broker_name
                and order["broker_number"] == broker_number
                and order["account_number"] == account_number
                and (action is None or order["action"] == action)
            ):

                # Process and remove the verified order
                process_verified_orders(broker_name, account_number, order)
                del incomplete_orders[key]
                logging.info(
                    f"Verified and removed temporary order for Account {account_number}"
                )
                break
        else:
            logging.error(
                f"No matching temporary order found for {broker_name} {broker_number}, Account {account_number}"
            )

    except Exception as e:
        logging.error(f"Error in handle_verification: {e}")


def process_verified_orders(broker_name, account_number, order):
    """Processes and finalizes a verified order by passing it to handle_complete_order."""
    logging.info(
        f"Verified order processed for {broker_name}, Account {account_number}:"
    )

    # Call handle_complete_order to complete and save the order to CSV
    handle_complete_order(
        broker_name,
        order["broker_number"],
        account_number,
        order["action"],
        order["quantity"],
        order["stock"],
    )
    logging.info("Order has been finalized and saved to CSV.")


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


def parse_manual_order_message(content):
    """Parses a manual order message and formats it for order processing.
    Expected format: 'manual Broker BrokerNumber Account OrderType Stock Price'
    """
    try:
        parts = content.split()
        if len(parts) != 7:
            raise ValueError(
                "Invalid format. Expected 'manual Broker BrokerNumber Account OrderType Stock Price'."
            )

        # Extract and format parts
        broker_name = parts[1]
        broker_number = parts[2].replace(":", "")  # Remove colon from Broker Number
        account_number = parts[3].replace(":", "")  # Remove colon from Account Number
        action = parts[4].capitalize()  # Capitalize order type (Buy/Sell)
        stock = parts[5].upper()  # Stock ticker symbol in uppercase
        price = float(parts[6])  # Convert Price to float
        quantity = 1.0  # Default quantity for manual orders

        # Current date in YYYY-MM-DD format
        date = datetime.now().strftime("%Y-%m-%d")

        # Normalize data
        broker_name, broker_number, action, quantity, stock, account_number = (
            normalize_order_data(
                broker_name, broker_number, action, quantity, stock, account_number
            )
        )

        # Structure the parsed data as order_data
        order_data = {
            "Broker Name": broker_name,
            "Broker Number": broker_number,
            "Account Number": account_number,
            "Order Type": action,
            "Stock": stock,
            "Quantity": quantity,
            "Price": price,
            "Date": date,
        }

        save_order_to_csv(order_data)

    except Exception as e:
        logging.error(f"Error parsing manual order: {e}")
        return None


def handle_failed_order(match, broker):
    try:
        # Extract the account number from the failure message
        account_number = match.group(1)

        # Loop through incomplete orders and remove the one matching the account number
        to_remove = []
        for (stock, account), order in incomplete_orders.items():
            if order["broker"] == "Firstrade" and account == account_number:
                to_remove.append((stock, account))
                logging.info(
                    f"Removing Firstrade order for account {account_number} due to failure."
                )

        # Remove failed accounts from incomplete_orders
        for item in to_remove:
            del incomplete_orders[item]

    except Exception as e:
        logging.error(f"Error handling failed order: {e}")


# -- Parsing Messages for Account Holdings


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
        return get_account_nickname(broker_name, group_number, account_number)
    except KeyError:
        # If the account is not found, return 'AccountNotMapped'
        return "AccountNotMapped"