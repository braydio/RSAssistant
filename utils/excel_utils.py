import json
import logging
import os
from copy import copy
from datetime import datetime

import openpyxl
from openpyxl.utils import get_column_letter

from utils.config_utils import (get_account_nickname, load_account_mappings,
                                load_config, send_large_message_chunks)

# Load configuration and mappings
config = load_config()
EXCEL_FILE_PATH = config['paths']['excel_log']
ORDERS_LOG_CSV = config['paths']['orders_log']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ACCOUNT_MAPPING = config['paths']['account_mapping']
ERROR_LOG_FILE = config['paths']['error_log']
ERROR_ORDER_DETAILS_FILE = config['paths']['error_order']

LOGGER_STOCK_ROW = config

ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Broker Name', 'Broker Number', 'Account', 'Stock', 'Quantity', 'Price', 'Total Value', 'Account Total']

stock_row = config['excel_log_settings']['stock_row']
date_row = config['excel_log_settings']['date_row']
account_start_row = config['excel_log_settings']['account_start_row']
account_start_column = config['excel_log_settings']['account_start_column']
split_ratio_placeholder = config['excel_log_settings']['split_ratio_placeholder']

# -- Config and Setup

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

# -- Update Account Mappings

async def index_account_details(ctx, excel_file=EXCEL_FILE_PATH, mapping_file=ACCOUNT_MAPPING):
    """Index account details from an Excel file, update account mappings in JSON, and notify about changes."""
    
    # Load the Excel workbook and select the 'Account Details' sheet
    try:
        wb = openpyxl.load_workbook(excel_file)
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

async def map_accounts_in_excel_log(ctx, excel_file=EXCEL_FILE_PATH, mapped_accounts_json=ACCOUNT_MAPPING):
    """Update the Reverse Split Log sheet and write account details back to the Account Details sheet."""

    # Load the Excel workbook and both sheets
    wb = openpyxl.load_workbook(excel_file)
    reverse_split_log = wb['Reverse Split Log']
    account_details_ws = wb['Account Details']

    # Load the account mappings from the JSON file
    with open(mapped_accounts_json, 'r') as f:
        account_mappings = json.load(f)

    # Settings for starting row/column
    account_start_row = 4  # Start at row 4 for account details
    account_start_column = 1  # Column 1 for account details (A)
    stock_row = 1  # The row where stock tickers are listed

    try:
        current_row = account_start_row

        # Iterate through brokers, group numbers, and accounts in the mapping
        for broker, broker_groups in account_mappings.items():
            if not isinstance(broker_groups, dict):
                await ctx.send(f"Error: broker_groups is not a dictionary for broker {broker}.")
                continue  # Skip this broker

            for group_number, accounts in broker_groups.items():
                if not isinstance(accounts, dict):
                    await ctx.send(f"Error: accounts is not a dictionary for group {group_number} in broker {broker}.")
                    continue  # Skip this group

                for account_number, nickname in accounts.items():
                    # Check if nickname is a string (which it should be)
                    if not isinstance(nickname, str):
                        await ctx.send(f"Error: nickname is not a string for account {account_number} in broker {broker}.")
                        continue

                    # Write the account nickname into the Reverse Split Log instead of the placeholder
                    reverse_split_log.cell(row=current_row, column=account_start_column, value=f"{broker} {nickname}")
                    print(f"Updating Reverse Split Log at row {current_row}, column {account_start_column} for {broker} {nickname}")

                    # Capture the cell reference in the Reverse Split Log
                    cell_reference = f"{reverse_split_log.cell(row=current_row, column=account_start_column).coordinate}"

                    # Update the Account Details sheet starting from the defined start row and column
                    account_details_ws.cell(row=current_row, column=account_start_column, value=broker)
                    account_details_ws.cell(row=current_row, column=account_start_column + 7, value=group_number)
                    account_details_ws.cell(row=current_row, column=account_start_column + 8, value=account_number)
                    account_details_ws.cell(row=current_row, column=account_start_column + 9, value=nickname)

                    print(f"Updating Account Details at row {current_row}: Broker: {broker}, Group: {group_number}, "
                          f"Account Number: {account_number}, Nickname: {nickname}")

                    current_row += 1  # Move to the next row for the next account

    except KeyError as e:
        await ctx.send(f"Missing key in account mappings: {e}")
        return
    except Exception as e:
        await ctx.send(f"Error updating Excel sheet: {e}")
        return

    # Save the updated workbook
    try:
        wb.save(excel_file)
        await ctx.send(f"Updated {excel_file} with account mappings.")
    except Exception as e:
        await ctx.send(f"Error saving Excel file: {e}")


# -- Logger Functions and Erroring

def update_excel_log(orders, order_type, excel_file_path=EXCEL_FILE_PATH, error_log_file=ERROR_LOG_FILE):
    """Update the Excel log with the buy or sell orders. If the Excel log can't be updated, write to a text log."""
    # print(orders)
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