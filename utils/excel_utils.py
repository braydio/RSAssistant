import openpyxl
from copy import copy
from openpyxl.utils import get_column_letter
from datetime import datetime
import os
import logging
from utils.config_utils import load_config, get_account_nickname

# Load configuration and mappings
config = load_config()
EXCEL_FILE_PATH = config['paths']['excel_log']
ORDERS_CSV_FILE = config['paths']['orders_log']
ACCOUNT_MAPPING = config['paths']['account_mapping']
ERROR_LOG_FILE = config['paths']['error_log']
ERROR_ORDER_DETAILS_FILE = config['paths']['error_order']

LOGGER_STOCK_ROW = config

ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Broker Name', 'Account', 'Stock', 'Quantity', 'Price', 'Total Value', 'Account Total']

# Load the Excel workbook and worksheet based on the configured path
def load_excel_log(file_path):
    if os.path.exists(file_path):
        return openpyxl.load_workbook(file_path)
    else:
        logging.error(f"Excel log not found: {file_path}")
        return None

async def add_stock_to_excel_log(ticker, split_date, excel_file_path=EXCEL_FILE_PATH):
    """Add the given stock ticker to the next available spot in the Excel log and copy formatting from the previous columns."""
    
    try:
        # Load config from YAML
        stock_row = config['excel_log_settings']['stock_row']  # E.g., '1' for row 1
        date_row = config['excel_log_settings']['date_row']    # E.g., '2' for row 2
        split_ratio_placeholder = config['excel_log_settings']['split_ratio_placeholder']  # E.g., "(S:S)"
        

        # Load the Excel workbook and the 'Reverse Split Log' sheet
        wb = load_excel_log(excel_file_path)
        print("Loaded Excel log workbook")
        if not wb:
            logging.error("Workbook could not be loaded.")
            return

        if 'Reverse Split Log' not in wb.sheetnames:
            logging.error("Sheet 'Reverse Split Log' not found in the workbook.")
            return
        ws = wb['Reverse Split Log']

        # Find the last filled column in the row where stock tickers are listed
        last_filled_column = find_last_filled_column(ws, stock_row)
        print(f"Last filled column: {last_filled_column}")

        # Find the next available columns for the ticker and split ratio
        ticker_col = last_filled_column + 1
        split_ratio_col = ticker_col + 1
        print(f"Next columns: ticker_col={ticker_col}, split_ratio_col={split_ratio_col}")

        # Copy the previous columns to maintain formatting
        copy_column(ws, last_filled_column, ticker_col)
        copy_column(ws, last_filled_column + 1, split_ratio_col)

        # Set the stock ticker and split ratio placeholder in the new columns
        ws.cell(row=stock_row, column=ticker_col).value = ticker
        ws.cell(row=stock_row, column=split_ratio_col).value = split_ratio_placeholder

        # Insert the split date one row above the stock ticker
        ws.cell(row=date_row, column=ticker_col).value = split_date

        # Save the workbook and close it
        wb.save(excel_file_path)
        logging.info(f"Added {ticker} to Excel log at column {get_column_letter(ticker_col)} with split date {split_date}.")

    except Exception as e:
        logging.error(f"Error adding stock to Excel log: {e}")
    finally:
        if wb:
            wb.close()

def find_last_filled_column(ws, row):
    """Find the last filled column in a given row."""
    last_filled_column = ws.max_column
    for col in range(3, ws.max_column + 1):  # Assuming first two columns are headers
        if ws.cell(row=row, column=col).value is None:
            last_filled_column = col - 1
            break
    return last_filled_column

def copy_column(worksheet, source_col, target_col):
    """Copy values and basic formatting from one column to another."""
    for row in range(1, worksheet.max_row + 1):
        source_cell = worksheet.cell(row=row, column=source_col)
        target_cell = worksheet.cell(row=row, column=target_col)

        # Copy the cell value and basic formatting (font, fill, border, alignment)
        target_cell.value = source_cell.value
        target_cell.font = copy(source_cell.font)
        target_cell.fill = copy(source_cell.fill)
        target_cell.border = copy(source_cell.border)
        target_cell.alignment = copy(source_cell.alignment)
        target_cell.number_format = source_cell.number_format  # Copy number format


import openpyxl
from copy import copy
from openpyxl.utils import get_column_letter
from datetime import datetime
import os
import logging
from utils.config_utils import load_config, get_account_nickname

# Load configuration and mappings
config = load_config()
EXCEL_FILE_PATH = config['paths']['excel_log']
ORDERS_CSV_FILE = config['paths']['orders_log']
ACCOUNT_MAPPING = config['paths']['account_mapping']
ERROR_LOG_FILE = config['paths']['error_log']
ERROR_ORDER_DETAILS_FILE = config['paths']['error_order']

def update_excel_log(orders, order_type, excel_file_path=EXCEL_FILE_PATH, error_log_file=ERROR_LOG_FILE):
    """Update the Excel log with the buy or sell orders. If the Excel log can't be updated, write to a text log."""
    
    wb = None  # Initialize wb to None to avoid UnboundLocalError

    try:
        # Use the globally loaded config object to get values like account_start_row and stock_row
        account_start_row = config['excel_log_settings']['account_start_row']  # E.g., '8'
        stock_row = config['excel_log_settings']['stock_row']  # E.g., '7'
        
        print(orders)  # Debugging: Print the orders to verify they are correct

        # Load the Excel workbook
        wb = load_excel_log(excel_file_path)
        if not wb:
            logging.error(f"Workbook could not be loaded: {excel_file_path}")
            return
        ws = wb.active  # Assuming the relevant sheet is the active one

        for order in orders:
            try:
                broker_name, account, order_type, stock, _, _, price = order

                # Normalize order type values
                if order_type == 'selling':
                    order_type = 'sell'
                elif order_type == 'buying':
                    order_type = 'buy'

                # Get the account nickname based on the broker and account pair
                mapped_name = get_account_nickname(broker_name, account)
                account_nickname = f"{broker_name} {mapped_name}"
                error_order = f"manual {broker_name} {account} {order_type} {stock} {price}"
                
                print(f"Excel - processing {order_type} order for {account_nickname}, stock: {stock}, price: {price}")

                # Find the row for the account in Column B
                account_row = None
                for row in range(account_start_row, ws.max_row + 1):
                    if ws[f'B{row}'].value == account_nickname:
                        account_row = row
                        break

                if account_row:
                    # Find the stock column in the specified stock row
                    stock_col = None
                    for col in range(3, ws.max_column + 1, 2):
                        if ws.cell(row=stock_row, column=col).value == stock:
                            stock_col = col + 1 if order_type.lower() == 'sell' else col
                            break

                    if stock_col:
                        # Update the price in the appropriate cell
                        ws.cell(row=account_row, column=stock_col).value = price
                        print(f"{account_nickname}: Updated column {stock_col}, row {account_row} with {price} for {order_type} on {stock}.")
                    else:
                        error_message = f"Stock {stock} not found for account {account_nickname}."
                        log_error_message(error_message, error_order, error_log_file)
                else:
                    error_message = f"Account {account_nickname} not found in Excel."
                    print(error_message)
                    log_error_message(error_message, error_order, error_log_file)

            except ValueError as e:
                error_message = f"ValueError: {str(e)}"
                log_error_message(error_message, error_order, error_log_file)
                return None

        # Save changes to the Excel file
        try:
            wb.save(excel_file_path)
            print(f"Saved Excel file: {excel_file_path}")
            logging.info(f"Successfully saved the Excel log: {excel_file_path}")
        except Exception as e:
            error_message = f"Failed to save Excel file: {excel_file_path}. Error: {str(e)}"
            print(error_message)
            log_error_message(error_message, "Excel save error", error_log_file)

    except Exception as e:
        logging.error(f"An error occurred while updating the Excel log: {e}")
    finally:
        if wb:  # Check if wb is not None before closing
            wb.close()


def log_error_message(error_message, order_details, error_log_file):
    """Log an error message to the specified log file and avoid duplicate entries."""
    # Read the current contents of the error log file
    try:
        with open(error_log_file, 'r') as log_file:
            log_contents = log_file.read()
    except FileNotFoundError:
        # If the log file doesn't exist, we'll create it later
        log_contents = ""

    # Check if the order details already exist in the log file
    if order_details in log_contents:
        print(f"Order details already logged as error: {order_details}")
        return  # Don't log duplicates

    # Append the error message and order details to the log file
    with open(error_log_file, 'a') as log_file:
        log_file.write(f"--- Error at {datetime.now()} ---\n")
        log_file.write(f"Error Message: {error_message}\n")
        log_file.write(f"Order Details: {order_details}\n\n")
    
    print(f"Written to log file: {error_log_file}")
    # Log the order details to a separate file for further processing
    log_error_order_details(order_details)


def log_error_order_details(error_order):
    """Log the order details for later manual entry for errors in a separate file."""
    try:
        with open(ERROR_ORDER_DETAILS_FILE, 'r') as order_file:
            existing_orders = order_file.read()
    except FileNotFoundError:
        existing_orders = ""

    # Avoid logging duplicate orders
    if error_order not in existing_orders:
        with open(ERROR_ORDER_DETAILS_FILE, 'a') as order_file:
            order_file.write(error_order + '\n')
        logging.info(f"Order details saved to {ERROR_ORDER_DETAILS_FILE}")


def remove_error(order_details):
    """Remove the order from both the error log and the order details log."""
    def remove_from_file(file_path, identifier):
        """Remove a block of text from a file based on the identifier."""
        try:
            with open(file_path, 'r') as file:
                lines = file.readlines()

            with open(file_path, 'w') as file:
                inside_error_block = False
                for line in lines:
                    if "--- Error at" in line and identifier in line:
                        inside_error_block = True

                    if inside_error_block and f"Order Details: {identifier}" in line:
                        inside_error_block = True

                    if inside_error_block and line.strip() == "":
                        inside_error_block = False
                        continue

                    if not inside_error_block:
                        file.write(line)

        except FileNotFoundError:
            logging.info(f"{file_path} not found. No need to remove anything.")

    remove_from_file(ERROR_LOG_FILE, order_details)
    print("Error removed from log.")
    remove_from_file(ERROR_ORDER_DETAILS_FILE, order_details)
    print("Error removed from error orders.")