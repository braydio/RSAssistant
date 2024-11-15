import csv
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta

import yfinance as yf
from discord import Embed

from utils.init import *
from utils.excel_utils import update_excel_log

# Load configuration and mappings
config = load_config()
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_LOG_CSV = config['paths']['orders_log']
HOLDINGS_DATA_FINAL = config['paths']['holdings_data']
ACCOUNT_MAPPING = config['paths']['account_mapping']

ORDERS_HEADERS = config['header_settings']['orders_headers']
HOLDINGS_HEADERS = config['header_settings']['holdings_headers']
EXCLUDED_BROKERS = config.get('excluded_brokers', {})

def ensure_csv_file_exists(file_path, headers):
    if not os.path.exists(file_path):
        with open(file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(headers)

def load_existing_orders(file_path):
    """Loads existing orders from CSV."""
    if os.path.exists(file_path):
        with open(file_path, mode='r', newline='') as file:
            reader = csv.DictReader(file)
            return list(reader)
    return []

def archive_stale_orders(existing_orders, cutoff_date, archive_path):
    """Archives stale orders older than the cutoff date."""
    stale_orders = [order for order in existing_orders if datetime.strptime(order['Date'], '%Y-%m-%d') < cutoff_date]
    if stale_orders:
        mode = 'a' if os.path.exists(archive_path) else 'w'
        with open(archive_path, mode=mode, newline='') as archive_file:
            writer = csv.DictWriter(archive_file, fieldnames=ORDERS_HEADERS)
            if mode == 'w':
                writer.writeheader()
            writer.writerows(stale_orders)
    return [order for order in existing_orders if order not in stale_orders]  # Return non-stale orders

def identify_latest_orders(orders, new_order):
    """Keeps the latest order for each unique key based on Timestamp."""
    new_order_key = (new_order['Broker Name'], new_order['Broker Number'], 
                     new_order['Account Number'], new_order['Order Type'].lower(), 
                     new_order['Stock'].upper(), new_order['Date'])
    
    # Dictionary to store the latest order by key
    latest_orders = {}
    for order in orders:
        order_key = (order['Broker Name'], order['Broker Number'], order['Account Number'], 
                     order['Order Type'].lower(), order['Stock'].upper(), order['Date'])
        
        # Only keep the latest order for each unique key
        if order_key not in latest_orders or order['Timestamp'] > latest_orders[order_key]['Timestamp']:
            latest_orders[order_key] = order
    
    # Add or replace with the new order if it's the latest
    if new_order_key in latest_orders:
        if new_order['Timestamp'] > latest_orders[new_order_key]['Timestamp']:
            logging.info(f"Replacing older duplicate with new order: {new_order}")
            latest_orders[new_order_key] = new_order
    else:
        latest_orders[new_order_key] = new_order
    
    return list(latest_orders.values())

def write_orders_to_csv(orders, file_path):
    """Writes orders to CSV, overwriting the file."""
    with open(file_path, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=ORDERS_HEADERS)
        writer.writeheader()
        writer.writerows(orders)

def save_order_to_csv(order_data):
    # Saves order, deletes duplicates and stale entries
    try:
        ensure_csv_file_exists(ORDERS_LOG_CSV, ORDERS_HEADERS)
        logging.info("Processing new order, checking for duplicates and stale entries.")

        # Add a current timestamp to the order data
        order_data['Timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Load existing orders
        existing_orders = load_existing_orders(ORDERS_LOG_CSV)

        # Archive stale orders
        cutoff_date = datetime.now() - timedelta(days=30)
        non_stale_orders = archive_stale_orders(existing_orders, cutoff_date, HOLDINGS_LOG_CSV)

        # Identify the latest orders to handle duplicates
        updated_orders = identify_latest_orders(non_stale_orders, order_data)

        # Write updated orders back to the CSV
        write_orders_to_csv(updated_orders, ORDERS_LOG_CSV)
        logging.info(f"Order saved to csv: {order_data} updating excel log.")

        update_excel_log(order_data)

    except Exception as e:
        logging.error(f"Unexpected error when saving order: {e}")

# -- Holdings Management

def save_holdings_to_csv(parsed_holdings):
    """Saves holdings data to CSV, ensuring no duplicates are saved, quantities are valid floats, and a timestamp is added."""
    
    # Generate the current timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Load existing holdings from the CSV
        existing_holdings = []
        if os.path.exists(HOLDINGS_LOG_CSV):
            with open(HOLDINGS_LOG_CSV, mode='r', newline='') as file:
                reader = csv.DictReader(file)
                existing_holdings = list(reader)

        # Create a set of unique keys to track existing entries (based on "Key", "Broker Name", "Broker Number", "Account Number", and "Stock")
        existing_keys = set(
            (holding['Key'], holding['Broker Name'], holding['Broker Number'], holding['Account Number'], holding['Stock'])
            for holding in existing_holdings
        )

        # Add "Timestamp" to HOLDINGS_HEADERS if not present
        if "Timestamp" not in HOLDINGS_HEADERS:
            HOLDINGS_HEADERS.append("Timestamp")

        # Convert parsed_holdings into a list of dictionaries and filter out duplicates
        new_holdings = []
        for holding in parsed_holdings:
            holding_dict = dict(zip(HOLDINGS_HEADERS, holding))  # Convert list to dictionary
            holding_key = (holding_dict['Key'], holding_dict['Broker Name'], holding_dict['Broker Number'], holding_dict['Account Number'], holding_dict['Stock'])

            # Ensure that 'Quantity', 'Price', and other numeric fields are valid floats
            try:
                holding_dict['Quantity'] = float(holding_dict['Quantity'])
                holding_dict['Price'] = float(holding_dict['Price'])  # Assuming you have a Price field to validate
                holding_dict['Position Value'] = float(holding_dict['Position Value'])  # Assuming this field as well
            except (ValueError, KeyError):
                logging.warning(f"Invalid numeric value in holding: {holding_dict}")
                continue  # Skip this entry if the values are not valid floats

            # Add timestamp to each new holding
            holding_dict["Timestamp"] = timestamp

            if holding_key not in existing_keys:  # Check if this combination already exists
                new_holdings.append(holding_dict)  # If not, add it to new holdings
                existing_keys.add(holding_key)     # Add the key to avoid future duplicates

        # Write updated holdings list back to the CSV
        if new_holdings:  # Proceed only if there are new holdings to add
            with open(HOLDINGS_LOG_CSV, mode='w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=HOLDINGS_HEADERS)
                writer.writeheader()  # Ensure headers are written
                writer.writerows(existing_holdings + new_holdings)  # Write the combined list

            logging.info(f"Holdings saved, with {len(new_holdings)} new entries added.")
        else:
            logging.info("No new holdings to add.")

    except Exception as e:
        logging.error(f"Error saving holdings: {e}")
        
def clear_holdings_log(filename):
    """
    Clears all holdings from the CSV file, preserving only the headers.
    Returns True if successful, False otherwise.
    """
    try:
        # Check if the file exists
        if not os.path.exists(filename):
            return False, f'Holdings at: "{filename}" does not exist.'

        # Read the headers from the file
        with open(filename, mode='r') as file:
            reader = csv.reader(file)
            headers = next(reader, None)  # Get the headers from the first row

        if headers:
            # Write only the headers back to the file, clearing the data
            with open(filename, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(headers)  # Write the headers back
            return True, f'Holdings at: "{filename}" has been cleared. Run `!rsa holdings` to repopulate.'
        else:
            return False, f'Holdings at: "{filename}" is empty or improperly formatted.'
    except Exception as e:
        return False, f"Error clearing holdings log: {e}"

