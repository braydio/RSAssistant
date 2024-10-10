import csv
import os
import logging
import yfinance as yf
from datetime import datetime, timedelta
from utils.config_utils import load_config, get_account_nickname
from utils.excel_utils import update_excel_log
from collections import defaultdict
from discord import Embed

# Load configuration and mappings
config = load_config()
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']
HOLDINGS_DATA_FINAL = config['paths']['holdings_data']
EXCEL_XLSX_FILE = config['paths']['excel_log']
ACCOUNT_MAPPING = config['paths']['account_mapping']

ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Broker Name', 'Account', 'Stock', 'Quantity', 'Price', 'Total Value', 'Account Total']

# Ensure CSV files exist
def ensure_csv_file_exists(file_path, headers):
    if not os.path.exists(file_path):
        with open(file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(headers)

def save_order_to_csv(broker_name, account_number, order_type, quantity, stock):
    """Saves order information to the orders CSV, removes duplicates, and removes stale orders."""
    print("Processing new order, checking for duplicates and stale entries.")
        
    try:
        # Load existing orders from the CSV
        existing_orders = []
        if os.path.exists(ORDERS_CSV_FILE):
            with open(ORDERS_CSV_FILE, mode='r', newline='') as file:
                reader = csv.DictReader(file)
                existing_orders = list(reader)

        # Define the cutoff for stale orders (e.g., 30 days)
        cutoff_date = datetime.now() - timedelta(days=30)

        # Remove duplicates and stale orders
        updated_orders = []
        new_order_key = (broker_name, account_number, order_type.lower(), stock.upper())

        for order in existing_orders:
            order_date = datetime.strptime(order['Date'], '%Y-%m-%d')
            order_key = (order['Broker Name'], order['Account Number'], order['Order Type'].lower(), order['Stock'].upper())

            if order_date < cutoff_date:
                # Skip stale orders
                continue

            if order_key == new_order_key:
                # Skip duplicates (keep the latest order, which will be added below)
                continue

            updated_orders.append(order)

        # Add the new order to the list
        current_time = datetime.now().strftime('%Y-%m-%d')
        new_order = {
            'Broker Name': broker_name,
            'Account Number': account_number,
            'Order Type': order_type.capitalize(),
            'Stock': stock.upper(),
            'Quantity': abs(float(quantity)),  # Ensure quantity is positive
            'Date': current_time
        }
        updated_orders.append(new_order)

        # Write the updated orders list back to the CSV
        with open(ORDERS_CSV_FILE, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=existing_orders[0].keys())
            writer.writeheader()
            writer.writerows(updated_orders)

        print(f"Order saved: {new_order}")
        price = get_last_stock_price(new_order['Stock'])
        print(price)

        account_nickname = get_account_nickname(broker_name, account_number)
        print(f"Updating excel log for {broker_name}, {account_nickname}, with order {order_type} {quantity} of {stock} at {price} on {current_time}")

        update_excel_log([[broker_name, account_number, order_type, stock, quantity, current_time, price]], order_type.lower(), EXCEL_XLSX_FILE)

    except ValueError as ve:
        logging.error(f"Error saving order due to value error: {ve}. Check quantity or stock.")
    except Exception as e:
        logging.error(f"Error saving order: {e}")

def update_holdings_data(order_type, broker_name, account_number, stock, quantity, price):
    """
    Updates holdings based on the order type ('buy' or 'sell'), broker, account, and stock details.
    """
    try:
        holdings_data = read_holdings_log()  # Read the current holdings
        key = (broker_name, account_number, stock)

        # Handle buy orders
        if order_type.lower() == 'buy':
            if key in holdings_data:
                # Update the quantity and price of an existing holding
                existing_quantity = float(holdings_data[key][3])
                new_quantity = existing_quantity + quantity
                # (Optional) Update the price or other details based on your business logic
                holdings_data[key][3] = new_quantity
                holdings_data[key][4] = price  # Optionally update the price
            else:
                # Add a new holding if it doesn't exist
                total_value = quantity * price
                holdings_data[key] = [broker_name, account_number, stock, quantity, price, total_value, None]
        
        # Handle sell orders
        elif order_type.lower() == 'sell':
            if key in holdings_data:
                existing_quantity = float(holdings_data[key][3])
                new_quantity = existing_quantity - quantity
                if new_quantity <= 0:
                    # Remove the stock from holdings if quantity is zero or negative
                    del holdings_data[key]
                else:
                    holdings_data[key][3] = new_quantity  # Update the quantity after selling
            else:
                logging.warning(f"Trying to sell stock not in holdings: {stock} in {broker_name} - {account_number}")
                return

        # Write updated holdings back to the CSV
        save_holdings_to_csv(holdings_data)

    except Exception as e:
        logging.error(f"Error updating holdings data: {e}")

def save_holdings_to_csv(holdings_data):
    """Saves holdings data to CSV."""
    try:
        with open(HOLDINGS_LOG_CSV, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(HOLDINGS_HEADERS)  # Write headers
            for key, entry in holdings_data.items():
                writer.writerow(entry)
    except Exception as e:
        logging.error(f"Error saving holdings: {e}")

def get_last_stock_price(stock):
    """
    Fetches the last price of the given stock using Yahoo Finance.
    """
    try:
        ticker = yf.Ticker(stock)
        stock_info = ticker.history(period="1d")
        if not stock_info.empty:
            last_price = stock_info['Close'].iloc[-1]
            return round(last_price, 2)  # Round to 2 decimal places for simplicity
            
        else:
            logging.warning(f"No stock data found for {stock}.")
            return None
    except Exception as e:
        logging.error(f"Error fetching last price for {stock}: {e}")
        return None

def read_holdings_log(file_path=HOLDINGS_LOG_CSV):
    """Reads holdings log to avoid duplicates."""
    holdings_data = {}
    try:
        if not os.path.exists(file_path):
            logging.info(f"{file_path} not found. Starting with an empty holdings log.")
            return holdings_data

        with open(file_path, mode='r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip the header row if there's one
            for row in reader:
                if len(row) == 7:
                    broker_name, account, stock, quantity, price, total, account_total = row
                    key = (broker_name, account, stock)
                    holdings_data[key] = [broker_name, account, stock, quantity, price, total, account_total]

    except Exception as e:
        logging.error(f"Error reading holdings log: {e}")
    
    return holdings_data

def get_holdings_for_summary(file_path=HOLDINGS_LOG_CSV):
    """Retrieves all holdings from the CSV for generating a profile summary."""
    holdings_data = []
    try:
        if os.path.exists(file_path):
            with open(file_path, mode='r') as file:
                reader = csv.reader(file)
                for row in reader:
                    if len(row) == 7:
                        holdings_data.append(row)
    except Exception as e:
        logging.error(f"Error reading holdings log: {e}")
    
    return holdings_data

