import csv
import os
import logging
import yfinance as yf
from datetime import datetime, timedelta
from utils.watch_utils import update_watch_list
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
    """Saves order information to the orders CSV and updates holdings accordingly."""
    print("Parsed new order, getting quantity, timestamp, price to save for excel log.")
    try:
        quantity = abs(float(quantity))  # Ensure quantity is positive
        current_time = datetime.now().strftime('%Y-%m-%d')
        price = get_last_stock_price(stock)
        print("Price from Last: ", price)

        # Save the order to the orders log
        with open(ORDERS_CSV_FILE, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([broker_name, account_number, order_type.capitalize(), stock, quantity, current_time])
        
            # Update the Excel log based on the order type
            update_excel_log([[broker_name, account_number, order_type, stock, quantity, current_time, price]], order_type.lower(), EXCEL_XLSX_FILE)

    except Exception as e:
        logging.error(f"Error saving order: {e}")


def update_holdings_data(order_type, broker_name, account_number, stock, quantity, price):
    """
    Updates holdings based on the order type ('buy' or 'sell'), broker, account, and stock details.
    """
    try:
        holdings_data = read_holdings_log()  # Read the current holdings
        key = (broker_name, account_number, stock)
        print(holdings_data)
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
            print(round(last_price, 2))
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

