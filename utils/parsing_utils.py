import re
import csv
import logging
import json
from discord import embeds
from datetime import datetime
from utils.csv_utils import save_order_to_csv, save_holdings_to_csv, read_holdings_log, get_holdings_for_summary
from utils.config_utils import load_config, get_account_nickname, load_account_mappings

config = load_config()

ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']
ORDERS_CSV_FILE = config['paths']['orders_log']

ORDERS_HEADERS = ['Broker Name', 'Account Number', 'Order Type', 'Stock', 'Quantity', 'Date']
HOLDINGS_HEADERS = ['Key', 'Broker Name', 'Account', 'Stock', 'Quantity', 'Price', 'Position Value', 'Account Total']


# Global variable to store incomplete Chase and Schwab orders
incomplete_orders = {}

# Regex patterns for various brokers
patterns = {
    'robinhood': r'(Robinhood)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'fidelity': r'(Fidelity)\s\d+\s(?:xxxxx|xxxx)?(\d+):\s(buy|sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
    'webull_buy': r'(Webull)\s\d+:\sbuying\s(\d+\.?\d*)\sof\s(\w+)',
    'webull_sell': r'(Webull)\s\d+:\ssell\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\w+):\s(Success|Failed)',
    'chase_buy_sell': r'(Chase)\s\d+:\s(buying|selling)\s(\d+\.?\d*)\sof\s(\w+)\s@\s(LIMIT|MARKET)',
    'chase_verification': r'(Chase)\s\d+\saccount\s(\d+):\sThe order verification was successful',
    'fennel': r'(Fennel)\s(\d+):\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sAccount\s(\d+):\s(Success|Failed)',
    'public': r'(Public)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'schwab_order': r'(Schwab)\s\d+\s(buying|selling)\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)',
    'schwab_verification': r'(Schwab)\s\d+\saccount\s(?:xxxx)?(\d+):\sThe order verification was successful',
    'bbae': r'(?i)(BBAE)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)'
}

def parse_order_message(content):
    """Parses an order message and extracts relevant details based on broker formats."""
   
    # Try to match each broker pattern
    for broker, pattern in patterns.items():
        match = re.match(pattern, content)
        if match:
            if broker == 'schwab_order' or broker == 'chase_buy_sell':  # Updated to 'schwab_order'
                handle_incomplete_order(match)
            elif broker == 'schwab_verification' or broker == 'chase_verification':
                handle_verification(match)
            else:
                handle_complete_order(match, broker)
            return
    
    print(f"Failed to parse order message: {content}") 

def handle_incomplete_order(match):
    
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)

    """Handles incomplete buy/sell orders for Chase and Schwab."""
    broker, action, quantity, stock, order_type = match.groups()[:5]
    
    if 'schwab' in broker.lower():
        schwab_accounts = account_mapping.get('Schwab', [])
        for account in schwab_accounts:
            # Add incomplete order for each account
            incomplete_orders[stock] = {
                'broker': broker,
                'action': action,
                'quantity': quantity,
                'stock': stock,
                'order_type': order_type
            }
            print(f"Handling incomplete order for Schwab account {account} - {action} {quantity} {stock} @ {order_type}")
    else:
        incomplete_orders[stock] = {
            'broker': broker,
            'action': action,
            'quantity': quantity,
            'stock': stock,
            'order_type': order_type
        }
        print(f"Handling incomplete order - {broker}, {action}, {quantity} {stock} @ {order_type}")

def handle_verification(match):
    """Handles order verification and completes the order for Chase and Schwab."""
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)  # Load once at the start
    
    broker, account_number = match.groups()[:2]
    
    if broker.lower() == 'schwab':
        schwab_accounts = account_mapping.get('Schwab', [])
        for account in schwab_accounts:
            for stock, order in incomplete_orders.items():
                if order['broker'] == broker:
                    save_order_to_csv(order['broker'], account, order['action'], order['quantity'], stock)
                    print(f"{broker}, Account {account}, Order verification successful for {stock}")
                    del incomplete_orders[stock]
                    return
    else:
        for stock, order in incomplete_orders.items():
            if order['broker'] == broker:
                save_order_to_csv(order['broker'], account_number, order['action'], order['quantity'], stock)
                print(f"{broker}, Account {account_number}, Order verification successful for {stock}")
                del incomplete_orders[stock]
                return

def handle_complete_order(match, broker):
    """Handles complete orders (Robinhood, Fidelity, Webull, Fennel, Public, BBAE)."""
    try:
        if broker == 'robinhood':
            broker, action, quantity, stock, account_number = match.groups()[:5]
            
        elif broker == 'fidelity':
            broker, account_number, action, quantity, stock = match.groups()[:5]
            
        elif broker == 'webull_buy':
            broker, quantity, stock = match.groups()[:3]
            account_number = 'N/A'  
            action = 'buy'
            
        elif broker == 'webull_sell':
            broker, quantity, stock, account_number = match.groups()[:4]
            if float(quantity) in [99.0, 999.0]:  # Specific check for Webull
                action = 'buy'
            else:
                action = 'sell'
                
        elif broker == 'fennel':
            broker, group_number, action, quantity, stock, account_number = match.groups()[:6]
            account_number = f"{group_number}{account_number}"  # Prepend group number to account number
            
        elif broker == 'public': 
            broker, action, quantity, stock, account_number = match.groups()[:5]  # This ensures account_number is extracted
            
        elif broker == 'bbae':
            broker, action, quantity, stock, account_number = match.groups()[:5]

        # Save the order details
        save_order_to_csv(broker, account_number, action, quantity, stock)
        print(f"{broker}, Account {account_number}, {action.capitalize()} {quantity} of {stock}")

    except Exception as e:
        print(f"Error handling complete order: {e}")

def parse_embed_message(embed, holdings_log_file):
    broker_name = embed.title.split(" Holdings")[0]

    for field in embed.fields:
        # Extract the account number from the message
        account_number = re.search(r'\((\w+)\)', field.name).group(1) if re.search(r'\((\w+)\)', field.name) else field.name

        # Get the account nickname using helper function
        account_key = broker_name + account_number
        print(f"Broker name | Account number : {broker_name} | {account_number}")

        # Read existing holdings log
        existing_holdings = []
        with open(holdings_log_file, 'r') as file:
            csv_reader = csv.reader(file)
            existing_holdings = [row for row in csv_reader if row[0] != account_key]

        # Parse the new holdings from the message
        new_holdings = []
        account_total = None
        for line in field.value.splitlines():
            match = re.match(r"(\w+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line)
            if match:
                stock = match.group(1)
                quantity = match.group(2)
                price = match.group(3)
                total_value = match.group(4)
                new_holdings.append([account_key, broker_name, account_number, stock, quantity, price, total_value])

            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

        # Append account total to all new holdings rows
        if account_total:
            for holding in new_holdings:
                holding.append(account_total)

        # Combine old and new holdings
        updated_holdings = existing_holdings + new_holdings

        # Write updated holdings to CSV
        with open(holdings_log_file, 'w', newline='') as file:
            csv_writer = csv.writer(file)
            # csv_writer.writerow(HOLDINGS_HEADERS)  # Write headers
            csv_writer.writerows(updated_holdings)

        print(f"Updated holdings for {account_key}.")

async def profile(ctx, broker_name):
    """Generates a profile summary for a broker and sends it to Discord."""
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
    holdings_log = read_holdings_log(HOLDINGS_LOG_CSV)  # Load the holdings data

    broker_name = broker_name.capitalize()
    broker_accounts = account_mapping.get(broker_name, {})

    if not broker_accounts:
        await ctx.send(f"No accounts found for {broker_name}.")
        return

    # Initialize variables
    summary_message = []
    processed_accounts = set()
    total_holdings = 0

    for key, row in holdings_log.items():
        log_broker, account = key[:2]
        account_total = float(row[5])  # Convert to float

        if log_broker != broker_name or account in processed_accounts:
            continue

        processed_accounts.add(account)
        total_holdings += account_total
        summary_message.append(f"| Account: {account}: ${account_total:.2f}")

    # Add total holdings to the message
    summary_message.insert(0, f"{broker_name} - Broker Summary\n${total_holdings:.2f} in {len(processed_accounts)} Accounts \n===========================")

    # Send the summary message to Discord
    await send_large_message_chunks(ctx, "\n".join(summary_message))

def get_fennel_account_number(account_str):
    """Extract Fennel account number by combining the first and second number from the string."""
    parts = account_str.split()
    if len(parts) >= 4 and parts[0].lower() == "fennel":
        # Combine the first number and the second number to form account number
        newpart = parts[3].split(")")[0]
        account_number = parts[1] + newpart
        return account_number
    return account_str  # Default behavior for non-Fennel accounts

async def track_ticker_summary(ctx, ticker, show_details=False, holding_logs_file=HOLDINGS_LOG_CSV, account_mapping_file=ACCOUNT_MAPPING_FILE):
    holdings = {}
    no_holdings = {}
    unique_accounts = {}
    ticker = ticker.upper()

    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)

    try:
        with open(account_mapping_file, 'r') as am_file:
            account_mapping = json.load(am_file)

        # Open the holdings log
        with open(holding_logs_file, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                broker_name = row['Broker Name']
                account = row['Account']

                # Handle Fennel specific account number parsing
                if broker_name.lower() == 'fennel':
                    account = get_fennel_account_number(account)
                else:
                    account = account[-4:]  # Last 4 digits for non-Fennel accounts

                stock = row['Stock'].upper()
                quantity = float(row['Quantity'])

                if broker_name not in holdings:
                    holdings[broker_name] = set()
                    no_holdings[broker_name] = set()
                    unique_accounts[broker_name] = set()

                unique_accounts[broker_name].add(account)

                if stock == ticker and quantity > 0:
                    holdings[broker_name].add(account)
                else:
                    no_holdings[broker_name].add(account)

        message = f"**{ticker} Holdings - All Brokerages**\n=============================\n"
        for broker, accounts in account_mapping.items():
            total = len(accounts)
            held_accounts = len(holdings.get(broker, []))
            message += f"| {broker} - Position in {held_accounts} of {total} accounts\n"

        if show_details:
            message += "\n**Ticker not in the following accounts:**\n"
            for broker, accounts in no_holdings.items():
                if accounts:
                    message += f"\n{broker}:\n"
                    for account in accounts:
                        account_nickname = get_account_nickname(broker, account)
                        logging.info()
                        # Check for matching orders in orders_log.csv
                        order_details = get_order_details(broker, account, ticker)
                        if order_details:
                            message += f"  {account_nickname} - Found transaction data: \n | {order_details}\n"
                        else:
                            message += f" {account_nickname} \n"

        await send_large_message_chunks(ctx, message)

    except FileNotFoundError:
        await ctx.send(f"Error: The file {holding_logs_file} or {account_mapping_file} was not found.")
    except KeyError as e:
        await ctx.send(f"Error: Missing expected column in CSV: {e}")
    except Exception as e:
        await ctx.send(f"Error: {e}")

def get_order_details(broker, account_number, ticker):
    """Search orders_log.csv for matching broker, account, and stock ticker."""
    try:
        with open(ORDERS_CSV_FILE, mode='r') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                # Handle Fennel specific account number parsing
                if broker.lower() == 'fennel':
                    account_in_csv = get_fennel_account_number(row['Account number'])
                else:
                    account_in_csv = row['Account number'][-4:]  # Last 4 digits for non-Fennel accounts

                if row['Broker'] == broker and account_in_csv == account_number and row['Stock'].upper() == ticker:
                    action = row['action'].capitalize()
                    quantity = row['quantity']
                    timestamp = row['timestamp']
                    return f"{action} {quantity} {ticker} {timestamp}"
        return None
    except FileNotFoundError:
        return None
    except KeyError as e:
        raise KeyError(f"Missing expected column in orders_log.csv: {e}")

async def send_large_message_chunks(ctx, message):
    # Discord messages have a max character limit of 2000
    if len(message) > 2000:
        # Split long messages into chunks
        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            await ctx.send(chunk)
    else:
        await ctx.send(message)