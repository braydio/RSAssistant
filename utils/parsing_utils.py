import re
import csv
import logging
from discord import embeds
from datetime import datetime
from utils.csv_utils import save_order_to_csv, save_holdings_to_csv, read_holdings_log, get_holdings_for_summary
from utils.config_utils import load_config, get_account_nickname, load_account_mappings

config = load_config()

ACCOUNT_MAPPING_FILE = config['paths']['account_mapping']
HOLDINGS_LOG_CSV = config['paths']['holdings_log']

# Global variable to store incomplete Chase and Schwab orders
incomplete_orders = {}

# Regex patterns for various brokers
patterns = {
    'robinhood': r'(Robinhood)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'fidelity': r'(Fidelity)\s\d+\s(?:xxxxx|xxxx)?(\d+):\s(sell)\s(\d+\.?\d*)\sshares\sof\s(\w+)',
    'webull_buy': r'(Webull)\s\d+:\sbuying\s(\d+\.?\d*)\sof\s(\w+)',
    'webull_sell': r'(Webull)\s\d+:\ssell\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\w+):\s(Success|Failed)',
    'chase_buy_sell': r'(Chase)\s\d+:\s(buying|selling)\s(\d+\.?\d*)\sof\s(\w+)\s@\s(LIMIT|MARKET)',
    'chase_verification': r'(Chase)\s\d+\saccount\s(\d+):\sThe order verification was successful',
    'fennel': r'(Fennel)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\sAccount\s(\d+):\s(Success|Failed)',
    'public': r'(Public)\s\d+:\s(buy|sell)\s(\d+\.?\d*)\sof\s(\w+)\sin\s(?:xxxxx|xxxx)?(\d+):\s(Success|Failed)',
    'schwab_buy': r'(Schwab)\s\d+\sbuying\s(\d+\.?\d*)\s(\w+)\s@\s(market|limit)',
    'schwab_verification': r'(Schwab)\s\d+\saccount\s(?:xxxx)?(\d+):\sThe order verification was successful'
}

def parse_order_message(content):
    """Parses an order message and extracts relevant details based on broker formats."""
    
    # Try to match each broker pattern
    for broker, pattern in patterns.items():
        match = re.match(pattern, content)
        if match:
            if broker == 'schwab_buy' or broker == 'chase_buy_sell':
                handle_incomplete_order(match)
            elif broker == 'schwab_verification' or broker == 'chase_verification':
                handle_verification(match)
            else:
                handle_complete_order(match, broker)
            return
    
    logging.error(f"Failed to parse order message: {content}")

def handle_incomplete_order(match):
    """Handles incomplete buy/sell orders for Chase and Schwab."""
    if 'schwab' in match.group(1).lower():
        # Schwab has 4 groups: broker, action, quantity, stock
        broker, action, quantity, stock = match.groups()[:4]
        order_type = "market"  # Default to market since Schwab doesn't specify
    else:
        # Chase has 5 groups: broker, action, quantity, stock, order_type
        broker, action, quantity, stock, order_type = match.groups()[:5]

    incomplete_orders[stock] = {
        'broker': broker,
        'action': action,
        'quantity': quantity,
        'stock': stock,
        'order_type': order_type
    }
    print(f"{broker}, {action.capitalize()} {quantity} of {stock} @ {order_type}")

def handle_verification(match):
    """Handles order verification and completes the order for Chase and Schwab."""
    broker, account_number = match.groups()[:2]

    for stock, order in incomplete_orders.items():
        if order['broker'] == broker:
            save_order_to_csv(order['broker'], account_number, order['action'], order['quantity'], stock)
            print(f"{broker}, Account {account_number}, Order verification successful for {stock}")
            del incomplete_orders[stock]
            return

def handle_complete_order(match, broker):
    """Handles complete orders (Robinhood, Fidelity, Webull, Fennel, Public)."""
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
        # Convert to 'buy' if quantity is 99 or 999
        if float(quantity) in [99.0, 999.0]:
            action = 'buy'
        else:
            action = 'sell'
    elif broker == 'fennel' or broker == 'public':
        broker, action, quantity, stock, account_number = match.groups()[:5]

    save_order_to_csv(broker, account_number, action, quantity, stock)
    print(f"{broker}, Account {account_number}, {action.capitalize()} {quantity} of {stock}")

# Function to parse holdings from an embed message
def parse_embed_message(embed, holdings_data):
    broker_name = embed.title.split(" Holdings")[0]
    existing_holdings = read_holdings_log()

    for field in embed.fields:
        account = field.name
        account_number = re.search(r'\((\w+)\)', account).group(1) if re.search(r'\((\w+)\)', account) else account
        account_label = get_account_nickname(broker_name, account_number)
        temp_holdings = []
        account_total = None

        for line in field.value.splitlines():
            if "buy" in line.lower() or "sell" in line.lower():
                order_type = "buy" if "buy" in line.lower() else "sell"
                match = re.search(r'(\d+\.\d+) of (\w+)', line)
                if match:
                    quantity = match.group(1)
                    stock = match.group(2)
                    save_order_to_csv(broker_name, account_number, order_type, quantity, stock)

            match = re.match(r"(\w+): (\d+\.\d+) @ \$(\d+\.\d+) = \$(\d+\.\d+)", line)
            if match:
                stock = match.group(1)
                quantity = match.group(2)
                price = match.group(3)
                total = match.group(4)
                temp_holdings.append([broker_name, account_label, stock, quantity, price, total])

            if "Total:" in line:
                account_total = line.split(": $")[1].strip()

                if temp_holdings:
                    for holding in temp_holdings:
                        holding.append(account_total)
                        key = (broker_name, account_label, holding[2])
                        if key not in existing_holdings:
                            holdings_data[key] = holding

    if holdings_data: 
        mapped_name = get_account_nickname(broker_name, account)
        account_nickname = (broker_name + " " + mapped_name)
        print("Mapped account name as: ", account_nickname, "With mapped name, broker name: ", mapped_name, broker_name)
        print(f"Processing sell order for account: {account_nickname}, stock: {stock}")
        save_holdings_to_csv(holdings_data)

async def profile(ctx, broker_name):
    """Generates a profile summary for a broker and sends it to Discord."""
    account_mapping = load_account_mappings(ACCOUNT_MAPPING_FILE)
    holdings_log = read_holdings_log(HOLDINGS_LOG_CSV)  # Load the holdings data


    broker_name = broker_name.capitalize()
    broker_accounts = account_mapping.get(broker_name, {})
    print(broker_accounts)

    if not broker_accounts:
        await ctx.send(f"No accounts found for {broker_name}.")
        return

    # Prepare the summary message
    # summary_message = [f"📊 **{broker_name}** - Brokerage Summary\nTotal Accounts: {len(broker_accounts)}"]
    summary_message = []

    # Create a set to track processed accounts (to avoid duplicates)
    processed_accounts = set()

    # Initialize total holdings across all accounts
    total_holdings = 0
    print(holdings_log)

    # Regex to match (D), (L), (B) accounts
    dre_account_regex = re.compile(r"\(D\)")
    etj_account_regex = re.compile(r"\(L\)")
    bch_account_regex = re.compile(r"\(B\)")

    # Find the latest entry for each account and stock
    for key, row in holdings_log.items():
        log_broker, account = key[:2]  # Unpack the broker and account from the key
        account_total = (row[5])  # Directly get account_total from the last value in `row`
        print(account_total, log_broker, account)
        print(account_total)

        # if dre_account_regex.search(account):  # (D) accounts
            # Specific logic for (D) accounts (if any)
            # log_broker = "Robinhood (Dre)"
            # print(account, log_broker)
            # summary_message.append(f"| (D) Account: {account}: ${account_total:.2f}")
        # elif etj_account_regex.search(account):  # (L) accounts
        #     # Specific logic for (L) accounts
        #     summary_message.append(f"| (L) Account: {account}: ${account_total:.2f}")
        # elif bch_account_regex.search(account):  # (B) accounts
        #     # Specific logic for (B) accounts
        #     summary_message.append(f"| (B) Account: {account}: ${account_total:.2f}")
        # else:
        #     # General accounts (if any accounts that don't match these regex)
        #     summary_message.append(f"| Other Account: {account}: ${account_total:.2f}")

        # Check if the log entry is for the correct broker
        if log_broker != broker_name:
            continue  # Skip entries that are not for the specified broker

        if account not in processed_accounts:
            processed_accounts.add(account)  # Mark this account as processed

            # Add account total to the overall total holdings
            total_holdings += account_total

            # Append account information to the summary message
            summary_message.append(f"| Account: {account}: ${account_total:.2f}")

    # Add total number of accounts
    summary_message.insert(0, f"{broker_name} - Broker Summary\n${total_holdings:.2f} in {len(processed_accounts)} Accounts \n===========================")

     # Send the summary message to Discord
    await send_large_message_chunks(ctx, "\n".join(summary_message))

# Function to send large messages in chunks
async def send_large_message_chunks(ctx, content, chunk_size=2000):
    for i in range(0, len(content), chunk_size):
        await ctx.send(f"```\n{content[i:i+chunk_size]}\n```")

# Function to track which brokerages/accounts are holding a specific ticker
async def track_ticker_summary(ctx, ticker, show_details=False, holding_logs_file=HOLDINGS_LOG_CSV):
    holdings = {}  # To store accounts with holdings for each broker
    total_accounts = {}  # To track total accounts per broker
    no_holdings = {}  # To store accounts with no holdings of the ticker
    ticker = ticker.upper()
    try:
        # Open the holding logs file
        with open(holding_logs_file, mode='r') as file:
            csv_reader = csv.DictReader(file)
            
            # Use a set to keep track of unique broker-account pairs processed
            processed_accounts = set()
            
            # Process each row in the CSV
            for row in csv_reader:
                broker_name = row['Broker Name']
                account = row['Account']
                stock = row['Stock']
                quantity = float(row['Quantity'])

                # Create a unique identifier for each broker-account pair
                broker_account_pair = (broker_name, account)

                # Skip this broker-account pair if we've already processed it
                if broker_account_pair in processed_accounts:
                    continue

                # Mark this broker-account pair as processed
                processed_accounts.add(broker_account_pair)

                # Initialize broker in holdings and no_holdings if not already present
                if broker_name not in holdings:
                    holdings[broker_name] = []
                    no_holdings[broker_name] = []

                    total_accounts[broker_name] = 0  # Count total accounts for each broker

                # Track total accounts per broker
                total_accounts[broker_name] += 1

                # Check if the account holds the specified ticker
                if stock == ticker and quantity > 0:
                    holdings[broker_name].append(account)  # Add to holdings if quantity is > 0
                else:
                    no_holdings[broker_name].append(account)  # Add to no holdings list

        # Prepare the top summary section
        message = f"**{ticker} Holdings - All Brokerages**\n=============================\n"
        for broker, total in total_accounts.items():
            held_accounts = len(holdings[broker]) if broker in holdings else 0
            message += f"| {broker} - Position in {held_accounts} of {total} accounts\n"

        # If "details" is passed, add detailed accounts without positions
        if show_details:
            message += "\n**Accounts without a position in the ticker:**\n"
            for broker, accounts in no_holdings.items():
                if accounts:
                    message += f"\n{broker}:\n"
                    for account in accounts:
                        message += f"  {account} does not have a position\n"

        # Send the message to Discord
        await send_large_message_chunks(ctx, message)

    except FileNotFoundError:
        await ctx.send(f"Error: The file {holding_logs_file} was not found.")
    except KeyError as e:
        await ctx.send(f"Error: Missing expected column in CSV: {e}")
    except Exception as e:
        await ctx.send(f"Error: {e}")

# Helper function to send large messages to Discord by splitting them into parts if necessary
async def send_large_message_chunks(ctx, message):
    # Discord messages have a max character limit of 2000
    if len(message) > 2000:
        # Split long messages into chunks
        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            await ctx.send(chunk)
    else:
        await ctx.send(message)