import logging
import os
import sqlite3
import uuid
from datetime import datetime

from utils.init import load_config, setup_logging

# Config and setup
config = load_config()
setup_logging()

DB_FILE = config.get("paths", {}).get("database", "volumes/db/reverse_splits.db")
os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)


# Database connection helper
def get_db_connection():
    """Helper function to get a database connection."""
    conn = sqlite3.connect(DB_FILE, timeout=30)  # Extend timeout to avoid lock errors
    conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode for better concurrency
    return conn


# Initialize the database tables
def init_db():
    """Initialize the database with all necessary tables."""

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.executescript(
            """
        CREATE TABLE IF NOT EXISTS AccountMappings (
            account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_number TEXT NOT NULL,
            account_nickname TEXT,
            broker_number TEXT
        );

        CREATE TABLE IF NOT EXISTS Orders (
            order_id TEXT PRIMARY KEY,
            account_id INTEGER,
            broker TEXT NOT NULL,
            broker_name TEXT NOT NULL,
            broker_number TEXT,
            account_number TEXT NOT NULL,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            total_value REAL NOT NULL,
            FOREIGN KEY (account_id) REFERENCES AccountMappings(account_id)
        );

        CREATE TABLE IF NOT EXISTS Holdings (
            holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            ticker TEXT NOT NULL,
            quantity REAL NOT NULL,
            average_price REAL NOT NULL,
            FOREIGN KEY (account_id) REFERENCES AccountMappings(account_id)
        );

        CREATE TABLE IF NOT EXISTS HistoricalHoldings (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            quantity REAL NOT NULL,
            average_price REAL NOT NULL,
            FOREIGN KEY (account_id) REFERENCES AccountMappings(account_id)
        );
        """
        )
        conn.commit()
    logging.info("Database initialized in sql_utils.")


def get_account_id(cursor, broker_name, broker_number, account_number):
    try:
        broker_name = str(broker_name)
        broker_number = str(broker_number)
        account_number = str(account_number)

        # Check if the account already exists
        cursor.execute(
            """
            SELECT account_id 
            FROM AccountMappings 
            WHERE broker = ? AND broker_number = ? AND account_number = ?
        """,
            (broker_name, broker_number, account_number),
        )
        result = cursor.fetchone()

        if result:
            return result[0]

        # Insert a new record and let SQLite auto-generate account_id
        cursor.execute(
            """
            INSERT INTO AccountMappings (broker, account_number, broker_number, account_nickname)
            VALUES (?, ?, ?, ?)
        """,
            (broker_name, account_number, broker_number, "AccountNotMapped"),
        )
        cursor.connection.commit()  # Explicit commit to release the lock

        return cursor.lastrowid
    except sqlite3.IntegrityError as e:
        logging.error(f"IntegrityError in get_account_id: {e}")
        raise


# Add an order to the Orders table
def add_order(order_data):
    """
    Adds a new order to the Orders table using order_data dictionary.
    """
    try:
        # Extract and validate data
        broker_name = str(order_data["Broker Name"])
        broker_number = str(order_data["Broker Number"])
        account_number = str(order_data["Account Number"])
        action = str(order_data["Order Type"])
        stock = str(order_data["Stock"])
        quantity = float(order_data["Quantity"])  # Ensure quantity is a float
        price = float(order_data["Price"])  # Ensure price is a float
        date = str(order_data["Date"])  # Ensure date is a valid string

        # Generate a unique order ID
        order_id = str(uuid.uuid4())

        # Compute the total value
        total_value = round(quantity * price, 2)

        # Retrieve or create the account ID
        with get_db_connection() as conn:
            cursor = conn.cursor()
            account_id = get_account_id(
                cursor, broker_name, broker_number, account_number
            )
            if account_id is None:
                raise ValueError(
                    "account_id is None. Ensure AccountMappings table has the correct entries."
                )

            # Log the data being inserted
            logging.debug(
                f"Inserting order: order_id={order_id}, account_id={account_id}, "
                f"broker_name={broker_name}, broker_number={broker_number}, "
                f"account_number={account_number}, stock={stock}, date={date}, "
                f"action={action}, quantity={quantity}, price={price}, total_value={total_value}"
            )

            # Insert the order into the Orders table
            cursor.execute(
                """
                INSERT INTO Orders (order_id, account_id, broker, broker_name, broker_number, account_number, 
                                    ticker, date, action, quantity, price, total_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order_id,
                    account_id,
                    broker_name,
                    broker_name,
                    broker_number,
                    account_number,
                    stock,
                    date,
                    action,
                    quantity,
                    price,
                    total_value,
                ),
            )
            conn.commit()
            logging.info(
                f"Order added for {stock}: {action} {quantity} shares @ {price}"
            )
    except KeyError as e:
        logging.error(f"Missing key in order_data: {e}")
        raise
    except ValueError as e:
        logging.error(f"Invalid data format in order_data: {e}")
        raise
    except sqlite3.Error as e:
        logging.error(f"Failed to add order for {stock}: {e}")
        raise

# Add
def insert_holdings(parsed_holdings):
    """
    Inserts parsed holdings into the Holdings and HistoricalHoldings tables.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        for holding in parsed_holdings:
            # Extract data from the parsed holding
            (
                account_key,
                broker_name,
                group_number,
                account_number,
                ticker,
                quantity,
                price,
                total_value,
                *optional,
            ) = holding

            # Retrieve or create the account_id (UUID)
            account_id = get_account_id(
                cursor, broker_name, group_number, account_number
            )

            # Insert into Holdings table
            cursor.execute(
                """
                INSERT OR REPLACE INTO Holdings (account_id, ticker, quantity, average_price)
                VALUES (?, ?, ?, ?)
            """,
                (account_id, ticker, quantity, price),
            )

            # Insert into HistoricalHoldings table
            cursor.execute(
                """
                INSERT INTO HistoricalHoldings (account_id, ticker, date, quantity, average_price)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    account_id,
                    ticker,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    quantity,
                    price,
                ),
            )

        conn.commit()
    logging.info(f"Inserted {len(parsed_holdings)} holdings into the database.")

# Add or update a holding in the Holdings table
def add_or_update_holding(account_id, ticker, quantity, price, operation="buy"):
    """
    Add or update a holding in the Holdings table.
    Parameters:
    - account_id: int - The account ID from AccountMappings.
    - ticker: str - The stock ticker symbol (e.g., "AAPL").
    - quantity: float - The number of shares being bought or sold.
    - price: float - The price per share.
    - operation: str - "buy" (default) to add to holdings, or "sell" to reduce holdings.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Check if the holding already exists
        cursor.execute(
            "SELECT quantity, average_price FROM Holdings WHERE account_id = ? AND ticker = ?",
            (account_id, ticker),
        )
        result = cursor.fetchone()

        if result:
            # Holding exists: Update it
            current_quantity, current_average_price = result
            if operation == "buy":
                # Recalculate the weighted average price and update quantity
                new_quantity = current_quantity + quantity
                new_average_price = (
                    (current_quantity * current_average_price) + (quantity * price)
                ) / new_quantity
                cursor.execute(
                    """
                    UPDATE Holdings
                    SET quantity = ?, average_price = ?
                    WHERE account_id = ? AND ticker = ?
                """,
                    (new_quantity, new_average_price, account_id, ticker),
                )
                conn.commit()
                logging.info(
                    f"Updated holding for {ticker}: New quantity={new_quantity}, Avg price={new_average_price}"
                )
            elif operation == "sell":
                # Ensure there's enough quantity to sell
                if quantity > current_quantity:
                    logging.error(
                        f"Cannot sell {quantity} shares of {ticker}; only {current_quantity} available."
                    )
                    raise ValueError(
                        f"Not enough shares of {ticker} to sell. Available: {current_quantity}"
                    )
                new_quantity = current_quantity - quantity
                # If quantity becomes zero, remove the holding
                if new_quantity == 0:
                    cursor.execute(
                        "DELETE FROM Holdings WHERE account_id = ? AND ticker = ?",
                        (account_id, ticker),
                    )
                    logging.info(
                        f"Holding for {ticker} sold completely and removed from Holdings."
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE Holdings
                        SET quantity = ?
                        WHERE account_id = ? AND ticker = ?
                    """,
                        (new_quantity, account_id, ticker),
                    )
                    logging.info(
                        f"Updated holding for {ticker}: New quantity={new_quantity}"
                    )
                conn.commit()
        else:
            # Holding does not exist: Add it
            if operation == "buy":
                cursor.execute(
                    """
                    INSERT INTO Holdings (account_id, ticker, quantity, average_price)
                    VALUES (?, ?, ?, ?)
                """,
                    (account_id, ticker, quantity, price),
                )
                conn.commit()
                logging.info(
                    f"Added new holding for {ticker}: Quantity={quantity}, Avg price={price}"
                )
            elif operation == "sell":
                logging.error(
                    f"Cannot sell {quantity} shares of {ticker}; holding does not exist."
                )
                raise ValueError(
                    f"Cannot sell shares of {ticker}. No existing holding."
                )

# --- Data Retrieval

def get_table_data(table_name, filters=None, limit=None):
    """
    Fetches data from a specified table with optional filters and a row limit.

    Args:
        table_name (str): Name of the table to query.
        filters (dict, optional): A dictionary of filters where the key is the column name 
                                  and the value is the filter value. For example: 
                                  {'account_id': 1}
        limit (int, optional): Maximum number of rows to fetch.

    Returns:
        list[dict]: A list of dictionaries representing the rows of the table.

    Raises:
        ValueError: If the table name is invalid.
        sqlite3.Error: For database-related errors.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Construct query
            query = f"SELECT * FROM {table_name}"
            params = []

            if filters:
                conditions = [f"{col} = ?" for col in filters.keys()]
                query += " WHERE " + " AND ".join(conditions)
                params = list(filters.values())

            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, params)
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()

            # Convert rows to list of dictionaries
            return [dict(zip(columns, row)) for row in rows]
    except sqlite3.Error as e:
        logging.error(f"Error querying table {table_name}: {e}")
        raise
    except ValueError as ve:
        logging.error(f"Invalid table name {table_name}: {ve}")
        raise


# -- Bot Commands

def bot_query_table(table_name, args):
    """
    Queries a table using arguments from a bot command.

    Args:
        table_name (str): Name of the table to query.
        args (list[str]): Arguments passed to the bot command. Supports filters (key=value)
                          and a limit (limit=n).

    Returns:
        list[dict]: Query results as a list of dictionaries.

    Raises:
        Exception: For invalid input or database errors.
    """
    filters = {arg.split("=")[0]: arg.split("=")[1] for arg in args if "=" in arg}
    limit = next((int(arg.split("=")[1]) for arg in args if arg.startswith("limit=")), None)
    return get_table_data(table_name, filters, limit)
