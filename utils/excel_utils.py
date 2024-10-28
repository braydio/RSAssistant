import json
import logging
import os
import shutil
from copy import copy
from datetime import datetime, timedelta

import openpyxl
from openpyxl.utils import get_column_letter

from utils.config_utils import (get_account_nickname, load_account_mappings,
                                load_config, send_large_message_chunks)

# Load configuration and mappings
config = load_config()
EXCEL_FILE_DIRECTORY = config['paths']['excel_directory']
EXCEL_FILE_NAME = config['paths']['excel_file_name']
BASE_EXCEL_FILE = config['paths']['base_excel_file']
ORDERS_LOG_CSV = config['paths']['orders_log']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ACCOUNT_MAPPING = config['paths']['account_mapping']
ERROR_LOG_FILE = config['paths']['error_log']
ERROR_ORDER_DETAILS_FILE = config['paths']['error_order']

ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Broker Name', 'Broker Number', 'Account', 'Stock', 'Quantity', 'Price', 'Total Value', 'Account Total']

# Load excel log settings
config_stock_row = config['excel_log_settings']['stock_row']
config_date_row = config['excel_log_settings']['date_row']
config_account_start_row = config['excel_log_settings']['account_start_row']
config_account_start_column = config['excel_log_settings']['account_start_column']
config_split_ratio_placeholder = config['excel_log_settings']['split_ratio_placeholder']
config_days_keep_backup = config['excel_log_settings']['days_keep_backup']


# -- Setup and Initialize Excel File

def get_excel_file_path(directory=EXCEL_FILE_DIRECTORY, filename=EXCEL_FILE_NAME):
    """
    Returns the path of the base Excel file (without date).
    If today's backup or tomorrow's backup doesn't exist, it creates them from the base file or today's file.
    """
    today = datetime.now().strftime("%m-%d")  # Format the date as MM-DD
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m-%d")

    # Full paths for today's and tomorrow's backup files
    today_excel_file = os.path.join(os.path.normpath(directory), f"Backup_{filename}.{today}.xlsx")
    tomorrow_excel_file = os.path.join(os.path.normpath(directory), f"Backup_{filename}.{tomorrow}.xlsx")
    
    # Path to the base file (this is the file we will use for reading/writing)
    base_excel_file = os.path.join(os.path.normpath(directory), BASE_EXCEL_FILE)
    
    # Ensure today's backup file exists (copy from base file if needed)
    if not os.path.exists(today_excel_file):
        if os.path.exists(base_excel_file):
            shutil.copy(base_excel_file, today_excel_file)
            print(f"Created today's backup Excel file: {today_excel_file}")
        else:
            print(f"Base Excel file {base_excel_file} not found.")

    # Ensure tomorrow's backup file exists (copy from today's backup if needed)
    if not os.path.exists(tomorrow_excel_file):
        if os.path.exists(today_excel_file):
            shutil.copy(today_excel_file, tomorrow_excel_file)
            print(f"Created tomorrow's backup Excel file: {tomorrow_excel_file}")
        else:
            print(f"Today's backup file {today_excel_file} not found.")

    # Return the path to the base file (this is the file you will use)
    return base_excel_file

excel_log_file = get_excel_file_path()

def load_excel_log(file_path):
    """Loads an Excel workbook, creates a new one if the file doesn't exist."""
    # Check if the base file exists
    if os.path.exists(file_path):
        print(f"Loading base Excel file: {file_path}")
        return openpyxl.load_workbook(file_path)
    else:
        logging.error(f"Base Excel log not found: {file_path}")
        return None


# -- Update Account Mappings

async def index_account_details(ctx, filename=excel_log_file, mapping_file=ACCOUNT_MAPPING):
    """Index account details from an Excel file, update account mappings in JSON, and notify about changes."""
    
    # Load the Excel workbook and select the 'Account Details' sheet
    try:
        wb = openpyxl.load_workbook(filename)
        if 'Account Details' not in wb.sheetnames:
            await ctx.send("Sheet 'Account Details' not found.")
            return
        ws = wb['Account Details']
    except Exception as e:
        await ctx.send(f"Error loading Excel file: {e}")
        return

    # Load the existing account mappings using the function from config_utils
    account_mappings = load_account_mappings(mapping_file)

    # Keep track of changes
    changes = []

    # Iterate through the rows of 'Account Details'
    try:
        for row in range(2, ws.max_row + 1):  # Start from row 2 (assuming row 1 has headers)
            broker_name = ws[f'A{row}'].value  # Broker name in column A
            group_number = ws[f'B{row}'].value  # Group number in column B
            account_number = str(ws[f'C{row}'].value).zfill(4)  # Account number in column C, padded to 4 digits
            account_nickname = ws[f'D{row}'].value  # Account nickname in column D

            if not broker_name or not group_number or not account_number or not account_nickname:
                continue  # Skip rows with missing data

            # Ensure all values are strings
            group_number = str(group_number)

            # Ensure the broker and group number exist in the JSON structure
            if broker_name not in account_mappings:
                account_mappings[broker_name] = {}
                changes.append(f"Added broker: {broker_name}")

            if group_number not in account_mappings[broker_name]:
                account_mappings[broker_name][group_number] = {}
                changes.append(f"Added group: {group_number} under broker {broker_name}")

            # Check if account number is already present and if the nickname has changed
            old_nickname = account_mappings[broker_name][group_number].get(account_number)
            if old_nickname != account_nickname:
                if old_nickname:
                    changes.append(f"Updated account {account_number} under broker {broker_name}, group {group_number} from '{old_nickname}' to '{account_nickname}'")
                else:
                    changes.append(f"Added new account {account_number} under broker {broker_name}, group {group_number} with nickname '{account_nickname}'")

            # Add or update the account details under the broker and group number
            account_mappings[broker_name][group_number][account_number] = account_nickname

    except Exception as e:
        await ctx.send(f"Error processing Excel rows: {e}")
        return

    # If there were any changes, send them via ctx.send
    if changes:
        change_message = "\n".join(changes)
        print(change_message)
    else:
        await ctx.send("No changes detected in account mappings.")

    # Save the updated mappings back to the JSON file
    try:
        with open(mapping_file, 'w') as f:
            json.dump(account_mappings, f, indent=4)
        await ctx.send(f"Updated mappings saved to `{mapping_file}`.")
        
    except Exception as e:
        await ctx.send(f"Error saving JSON file: {e}")

async def map_accounts_in_excel_log(ctx, filename=excel_log_file, mapped_accounts_json=ACCOUNT_MAPPING):
    """Update the Reverse Split Log sheet by inserting new rows, copying data and formatting, and deleting original rows."""

    # Load the Excel workbook and the Reverse Split Log sheet
    wb = openpyxl.load_workbook(filename)
    reverse_split_log = wb['Reverse Split Log']

    # Load the account mappings from the JSON file
    with open(mapped_accounts_json, 'r') as f:
        account_mappings = json.load(f)

    try:
        # Step 1: Find rows that contain 'Totals' (case-insensitive) and mark them as protected
        protected_rows = set()  # To store the protected rows (Totals, and the rows above and below)

        # Loop through the entire sheet to find 'Totals'
        for row in range(1, reverse_split_log.max_row + 1):
            for col in range(1, reverse_split_log.max_column + 1):
                cell_value = reverse_split_log.cell(row=row, column=col).value
                if cell_value and isinstance(cell_value, str) and 'totals' in cell_value.lower():
                    # Add the row with 'Totals' and the rows above and below to the protected set
                    protected_rows.add(row)  # The row with 'Totals'
                    if row > 1:  # Protect the row above if it exists
                        protected_rows.add(row - 1)
                    if row < reverse_split_log.max_row:  # Protect the row below if it exists
                        protected_rows.add(row + 1)
                    break  # Stop checking other columns once 'Totals' is found in the row

        # Step 2: Count the total number of accounts in the mappings
        total_accounts = sum(len(accounts) for broker_groups in account_mappings.values() for accounts in broker_groups.values())

        # Insert the required number of new rows above the start row
        reverse_split_log.insert_rows(config_account_start_row, total_accounts)

        current_row = config_account_start_row

        # Step 3: Iterate through brokers, group numbers, and accounts in the mapping
        for broker, broker_groups in account_mappings.items():
            for group_number, accounts in broker_groups.items():
                for account_number, nickname in accounts.items():
                    # Skip copying into protected rows
                    while current_row in protected_rows:
                        current_row += 1  # Move to the next unprotected row

                    # Insert the account name in the new rows
                    reverse_split_log.cell(row=current_row, column=config_account_start_column, value=f"{broker} {nickname}")

                    # Look for the matching account in the original rows and transfer log data
                    account_found = False
                    for row in range(config_account_start_row + total_accounts, reverse_split_log.max_row + 1):
                        account_in_log = reverse_split_log.cell(row=row, column=config_account_start_column).value
                        if account_in_log == f"{broker} {nickname}":
                            # Ensure we don't overwrite protected rows during copying
                            if row not in protected_rows:
                                account_found = True
                                # Copy both values and formatting from the original row to the new row
                                copy_values_and_formatting(reverse_split_log, row, current_row)
                            break

                    if not account_found:
                        # If no matching log data is found, leave the log data empty or set a default
                        for col in range(2, reverse_split_log.max_column + 1):
                            reverse_split_log.cell(row=current_row, column=col).value = None  # Or set a default value

                    current_row += 1  # Move to the next row for the next account

        # Step 4: Delete the original rows after transferring data, skipping protected rows
        rows_to_delete = set(range(config_account_start_row + total_accounts, reverse_split_log.max_row + 1)) - protected_rows
        for row in sorted(rows_to_delete, reverse=True):
            reverse_split_log.delete_rows(row)

    except KeyError as e:
        await ctx.send(f"Missing key in account mappings: {e}")
        return
    except Exception as e:
        await ctx.send(f"Error updating Excel sheet: {e}")
        return

    # Save the updated workbook
    try:
        wb.save(filename)
        await ctx.send(f"Updated {filename} with account mappings.")
    except Exception as e:
        await ctx.send(f"Error saving Excel file: {e}")

async def clear_account_mappings(ctx, mapping_file=ACCOUNT_MAPPING):
    """Clear the account mappings JSON file and notify the user."""

    try:
        # Clear the account mappings by writing an empty dictionary to the file
        with open(mapping_file, 'w') as f:
            json.dump({}, f, indent=4)

        # Notify the user that the file has been cleared
        await ctx.send(f"Account mappings in `{mapping_file}` have been cleared.")
    
    except Exception as e:
        await ctx.send(f"Error clearing the JSON file: {e}")

def copy_values_and_formatting(worksheet, source_row, target_row):
    """Copy both values and formatting from a source row to a target row in the worksheet."""
    for col in range(1, worksheet.max_column + 1):  # Loop over each column
        source_cell = worksheet.cell(row=source_row, column=col)
        target_cell = worksheet.cell(row=target_row, column=col)

        # Copy the cell value
        target_cell.value = source_cell.value

        # Copy formatting (font, fill, border, alignment, and number format)
        if source_cell.has_style:
            target_cell.font = copy(source_cell.font)
            target_cell.fill = copy(source_cell.fill)
            target_cell.border = copy(source_cell.border)
            target_cell.alignment = copy(source_cell.alignment)
            target_cell.number_format = source_cell.number_format

# -- Watchlist New Stock Functions

async def add_stock_to_excel_log(ctx, ticker, split_date):
    """Add the given stock ticker to the next available spot in the Excel log and copy formatting from the previous columns."""
    
    try:
        # Load config from YAML
        stock_row = config['excel_log_settings']['stock_row']  # E.g., '1' for row 1
        date_row = config['excel_log_settings']['date_row']    # E.g., '2' for row 2
        split_ratio_placeholder = config['excel_log_settings']['split_ratio_placeholder']  # E.g., "(S:S)"
        
        # Load the Excel workbook and the 'Reverse Split Log' sheet (no await because it's a sync operation)
        wb = load_excel_log(excel_log_file)
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
        spacer_col = split_ratio_col +1
        print(f"Next columns: ticker_col={ticker_col}, split_ratio_col={split_ratio_col}")

        # Copy the previous columns to maintain formatting
        copy_column(ws, last_filled_column, ticker_col)
        copy_column(ws, last_filled_column + 1, split_ratio_col)
        copy_column(ws, last_filled_column + 1, spacer_col)

        # Set the stock ticker and split ratio placeholder in the new columns
        ws.cell(row=stock_row, column=ticker_col).value = ticker
        ws.cell(row=stock_row, column=split_ratio_col).value = split_date

        # Insert the split date one row above the stock ticker
        ws.cell(row=date_row, column=ticker_col).value = split_date

        # Save the workbook and close it (no await)
        wb.save(excel_log_file)
        logging.info(f"Added {ticker} to Excel log at column {get_column_letter(ticker_col)} with split date {split_date}.")
        
        await ctx.send(f"Added {ticker} to Excel log at column {get_column_letter(ticker_col)} with split date {split_date}.")

    except Exception as e:
        logging.error(f"Error adding stock to Excel log: {e}")
    finally:
        if wb:
            wb.close()

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

def find_last_filled_column(ws, row):
    """Find the last filled column in a given row."""
    last_filled_column = ws.max_column
    for col in range(3, ws.max_column + 1):  # Assuming first two columns are headers
        if ws.cell(row=row, column=col).value is None:
            last_filled_column = col - 1
            break
    return last_filled_column


# -- Logger Functions and Erroring

def update_excel_log(orders, order_type, filename=excel_log_file, config=config):
    """Update the Excel log with the buy or sell orders, save with a date-based filename, and manage backups."""

    wb = None  # Initialize wb to None to avoid UnboundLocalError
    error_log_file = ERROR_LOG_FILE

    try:
        # Load the Excel workbook
        wb = load_excel_log(filename)  # Function that loads the workbook
        if not wb:
            logging.error(f"Workbook could not be loaded: {filename}")
            return

        # Ensure we're working with the 'Reverse Split Log' sheet
        if "Reverse Split Log" in wb.sheetnames:
            ws = wb["Reverse Split Log"]
        else:
            # Create the sheet if it doesn't exist
            ws = wb.create_sheet("Reverse Split Log")
            logging.info(f"'Reverse Split Log' sheet was missing, created a new one.")

        # Use the globally loaded config object to get values like account_start_row and stock_row
        accounts_row = config['excel_log_settings']['account_start_row']
        stock_row = config['excel_log_settings']['stock_row']
        account_start_column = config['excel_log_settings']['account_start_column']
        days_keep_backup = config['excel_log_settings']['days_keep_backup']

        print(orders)  # Debugging: Print the orders to verify they are correct

        for order in orders:
            try:
                broker_name, broker_number, account, order_type, stock, _, _, price = order
                error_order = f"manual {broker_name} {broker_number} {account} {order_type} {stock} {price}"
                print(error_order)

                # Normalize order type values
                if order_type == 'selling':
                    order_type = 'sell'
                elif order_type == 'buying':
                    order_type = 'buy'

                # Get the account nickname based on the broker and account pair
                mapped_name = get_account_nickname(broker_name, broker_number, account)
                account_nickname = f"{broker_name} {mapped_name}"

                print(f"Excel - processing {order_type} order for {account_nickname}, stock: {stock}, price: {price}")

                # Find the row for the account in Column A (using the config value)
                account_row = None
                for row in range(accounts_row, ws.max_row + 1):
                    # Ensure we are checking Column A
                    print(f"Checking column A, row {row}: {ws[f'A{row}'].value}")
                    cell_value = ws[f'A{row}'].value
                    # Check if the cell value is a string before using strip
                    if isinstance(cell_value, str):
                        cell_value = cell_value.strip()  # Strip whitespace if it's a string
                    else:
                        cell_value = str(cell_value) if cell_value is not None else ''  # Convert non-string to string

                    print(f"Checking row {row}: {cell_value}")  # Debugging: Print the cell value being checked
                    if cell_value.lower() == account_nickname.strip().lower():  # Case-insensitive comparison
                        account_row = row
                        break

                if account_row:
                    # Find the stock column in the specified stock row (using the config value)
                    stock_col = None
                    for col in range(3, ws.max_column + 1, 2):
                        if ws.cell(row=stock_row, column=col).value == stock:
                            stock_col = col + 1 if order_type.lower() == 'sell' else col
                            break

                    if stock_col:
                        # Update the price in the appropriate cell
                        ws.cell(row=account_row, column=stock_col).value = price
                        print(f"{account_nickname}: Updated column {stock_col}, row {account_row} with {price} for {order_type} on {stock}.")

                        # Remove the corresponding error from the error logs if the order was successfully processed
                        remove_from_file(error_log_file, error_order)
                        remove_from_file(ERROR_ORDER_DETAILS_FILE, error_order)
                    else:
                        error_message = f"Stock {stock} not found for account {account_nickname}."
                        log_error_message(error_message, error_order, error_log_file)
                else:
                    error_message = f"Account {account_nickname} not found in Excel."
                    print(f"Account not found: {account_nickname}")  # Debugging: Print the account name
                    log_error_message(error_message, error_order, error_log_file)

            except ValueError as e:
                error_message = f"ValueError: {str(e)}"
                log_error_message(error_message, error_order, error_log_file)
                return None

        # Save changes to the Excel file
        try:
            wb.save(filename)
            print(f"Saved Excel file: {filename}")
            logging.info(f"Successfully saved the Excel log: {filename}")

            # Manage backups by removing stale ones (using the config value)
            delete_stale_backups(EXCEL_FILE_DIRECTORY, days_keep_backup)

        except Exception as e:
            error_message = f"Failed to save Excel file: {filename}. Error: {str(e)}"
            print(error_message)
            log_error_message(error_message, "Excel save error", error_log_file)

    except Exception as e:
        # Catch any encoding-related errors here
        logging.error(f"An error occurred while updating the Excel log: {str(e)}")

    finally:
        if wb:  # Check if wb is not None before closing
            wb.close()



def delete_stale_backups(directory=EXCEL_FILE_DIRECTORY, days_to_keep=config_days_keep_backup):
    """Delete backup files older than the specified number of days."""
    now = datetime.now()
    cutoff = now - timedelta(days=days_to_keep)
    
    # Iterate through files in the directory
    for filename in os.listdir(directory):
        # Match files that follow the "ReverseSplitLog.MM-DD.xlsx" format
        if filename.startswith("Backup") and filename.endswith(".xlsx"):
            # Extract the date part (MM-DD) from the filename
            try:
                date_part = filename.split("ReverseSplitLog.")[1].split(".xlsx")[0]
                file_date = datetime.strptime(date_part, "%m-%d")
                
                # Update the file date to the current year for comparison
                file_date = file_date.replace(year=now.year)
                
                # Check if the file is older than the cutoff date
                if file_date < cutoff:
                    file_path = os.path.join(directory, filename)
                    print(f"Deleting old backup file: {filename}")
                    os.remove(file_path)
                    logging.info(f"Deleted old backup file: {filename}")
            
            except ValueError:
                logging.error(f"Failed to parse date from filename: {filename}")
                continue

def log_error_message(error_message, order_details, error_log_file=ERROR_LOG_FILE):
    """Log an error message to the specified log file and avoid duplicate entries."""
    print(order_details)
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
    log_error_order_details(order_details)

def log_error_order_details(order_details):
    print(order_details)
    """Log the order details for later manual entry for errors in a separate file."""
    try:
        logging.info(order_details)
        with open(ERROR_ORDER_DETAILS_FILE, 'r') as order_file:
            existing_orders = order_file.read()
    except FileNotFoundError:
        existing_orders = ""

    # Avoid logging duplicate orders
    if order_details not in existing_orders:
        with open(ERROR_ORDER_DETAILS_FILE, 'a') as order_file:
            order_file.write(order_details + '\n')
        logging.info(f"Order details saved to {ERROR_ORDER_DETAILS_FILE}")

def remove_from_file(file_path, identifier):
    print(f'Removing {identifier} from {file_path}')
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()

        with open(file_path, 'w') as file:
            block_to_skip = False
            for line in lines:
                if "--- Error at" in line:
                    block_to_skip = False
                if f"Order Details: {identifier}" in line:
                    block_to_skip = True
                if not block_to_skip:
                    file.write(line)
    except FileNotFoundError:
        logging.info(f"{file_path} not found. No need to remove anything.")
