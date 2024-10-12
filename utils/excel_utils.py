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

ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Broker Name', 'Account', 'Stock', 'Quantity', 'Price', 'Total Value', 'Account Total']

# Load the Excel workbook and worksheet based on the configured path
def load_excel_log(file_path):
    if os.path.exists(file_path):
        return openpyxl.load_workbook(file_path)
    else:
        logging.error(f"Excel log not found: {file_path}")
        return None

def add_stock_to_excel_log(ticker, excel_file_path):
    """Add the given stock ticker to the next available spot in the Excel log, and copy formatting from the previous columns."""
    print("addings.")
    try:
        # Load the Excel workbook and get the active worksheet
        wb = load_excel_log(excel_file_path)
        if not wb:
            return
        ws = wb.active

        stock_row = 7  # Row where stock tickers are listed (B7 and onward)
        date_row = 6  # Row that has the date

        # Find the last filled column in row 7
        last_filled_column = ws.max_column
        for col in range(3, ws.max_column + 1):  # Start checking from B onwards
            if ws.cell(row=stock_row, column=col).value is None:
                last_filled_column = col - 1
                break
        # print(f"Last filled column: {last_filled_column}")

        # Find bottom filled row in the last filled column
        bottom_row = ws.max_row
        for row in range(6, ws.max_row + 1):
            if ws.cell(row=row, column=last_filled_column).value is None:
                bottom_row = row - 1
                break
        # print(f"Bottom filled row: {bottom_row}")

        start_col = last_filled_column
        # start_row = date_row
        next_ticker_col = start_col + 1
        next_split_ratio_col = next_ticker_col + 1
        # end_row = bottom_row
        # Copy the previous two columns to the new ones
        print(f"Copying column {start_col} to column {next_ticker_col}")
        print(f"Copying column {start_col} to column {next_ticker_col + 1}")
        copy_column(ws, start_col, next_ticker_col)
        copy_column(ws, start_col, next_ticker_col + 1)

        print(f"Inserting ticker in column {next_ticker_col} and placeholder S:S in column {next_split_ratio_col}")
        # Set the stock ticker in the next available cell
        ws.cell(row=stock_row, column=next_ticker_col).value = ticker
        # Set placeholder "S:S" in the next column
        ws.cell(row=stock_row, column=next_split_ratio_col).value = "S:S"
        print("Added ticker and split ratio")

        # Insert the current date one row above the stock ticker
        current_date = datetime.now().strftime("%Y-%m-%d")
        ws.cell(row=date_row, column=next_ticker_col).value = current_date
        print(f"Inserted date {current_date} at row {date_row}, column {next_ticker_col}")

        # Save the workbook with updated log
        wb.save(excel_file_path)
        wb.close()
        logging.info(f"Added {ticker} to Excel log at {get_column_letter(next_ticker_col)}{stock_row}.")

    except Exception as e:
        logging.error(f"Error adding stock to Excel log: {e}")

def copy_column(worksheet, source_col, target_col):
    """Copy values and basic formatting from one column to another."""
    for row in range(1, worksheet.max_row + 1):
        source_cell = worksheet.cell(row=row, column=source_col)
        target_cell = worksheet.cell(row=row, column=target_col)

        # Copy the cell value
        target_cell.value = source_cell.value

        # Copy basic formatting (font, fill, border, alignment)
        target_cell.font = copy(source_cell.font)
        target_cell.fill = copy(source_cell.fill)
        target_cell.border = copy(source_cell.border)
        target_cell.alignment = copy(source_cell.alignment)
        target_cell.number_format = source_cell.number_format  # Copy number format

        # Now clear the values in the source column after copying
        clear_column_values(worksheet, target_col)

def clear_column_values(worksheet, column):
    """Set all the cell values in a given column to None (i.e., blank the cells)."""
    for row in range(1, worksheet.max_row + 1):
        worksheet.cell(row=row, column=column).value = None
    
def update_excel_log(orders, order_type, excel_file_path):
    """Update the Excel log with the buy or sell orders."""
    print(orders)  # Debugging: Print the orders to verify they are correct
    
    # Load the Excel workbook
    wb = load_excel_log(EXCEL_FILE_PATH)
    if not wb:
        return
    ws = wb.active  # Assuming the relevant sheet is the active one

    # Define the row and column offsets
    account_start_row = 8  # Accounts start at row 8 (B8)
    stock_row = 7          # Tickers are listed starting row 7 (B7)

    for order in orders:
        try:
            broker_name, account, order_type, stock, _, _, price = order
            if order_type == 'selling':
                order_type = 'sell'
            if order_type == 'buying':
                order_type = 'buy'

            # Get the account nickname based on the broker and account pair
            mapped_name = get_account_nickname(broker_name, account)
            account_nickname = f"{broker_name} {mapped_name}"
            print(f"Excel - processing {order_type} order for {account_nickname}, stock: {stock}, price: {price}")

            # Find the row for the account in Column B
            account_row = None
            for row in range(account_start_row, ws.max_row + 1):
                if ws[f'B{row}'].value == account_nickname:
                    account_row = row
                    break

            if account_row:
                # Find the stock column in Row 7
                stock_col = None
                for col in range(3, ws.max_column + 1, 2):
                    if ws.cell(row=stock_row, column=col).value == stock:
                        stock_col = col + 1 if order_type.lower() == 'sell' else col
                        break

                if stock_col:
                    # Update the price in the appropriate cell
                    ws.cell(row=account_row, column=stock_col).value = price
                    print(f"{account_nickname} column number {col} row {row} entering {price} as {order_type} for {stock}")
                    # print(f"Updated {order_type} price for {account_nickname} - {stock} in Excel.")
                else:
                    print(f"Stock {stock} not found for account {account_nickname}.")
            else:
                print(f"Account {account_nickname} not found in Excel.")

        except ValueError as e:
            print(f"Error processing order {order}: {e}")
            continue

    # Save changes to the Excel file
    wb.save(excel_file_path)
    print(f"Saved excel {excel_file_path}")
    wb.close()
