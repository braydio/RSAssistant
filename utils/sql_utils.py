import asyncio
import logging
import os
import sqlite3
import uuid
from datetime import datetime

from utils.config_utils import SQL_DATABASE_DB_V1, load_config, setup_logging

# Config and setup
config = load_config()
setup_logging()

PRIMARY_DB_FILE = SQL_DATABASE_DB_V1  # config.get("paths", {}).get("database", "volumes/db/reverse_splits.db")

# Database connection helper
def get_db_connection():
    """Helper function to get a database connection."""
    logging.debug("Attempting to establish a database connection.")
    try:
        conn = sqlite3.connect(PRIMARY_DB_FILE, timeout=30)  # Extend timeout to avoid lock errors
        conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode for better concurrency
        logging.debug("Database connection established successfully.")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Error establishing database connection: {e}")
        raise

def get_or_create_account_id(broker, broker_number, account_number, account_nickname="AccountNotMapped"):
    """
    Retrieves the account_id for a given broker and account number. If it doesn't exist, it creates a new entry.
    """
    logging.info(f"Fetching or creating account ID for broker: {broker}, broker_number: {broker_number}, account_number: {account_number}.")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            # Check if the account exists
            cursor.execute(
                """
                SELECT account_id
                FROM Accounts
                WHERE broker = ? AND broker_number = ? AND account_number = ?
                """,
                (broker, broker_number, account_number),
            )
            result = cursor.fetchone()

            if result:
                logging.debug(f"Account ID found: {result[0]}.")
                return result[0]

            # Create the account if it doesn't exist
            cursor.execute(
                """
                INSERT INTO Accounts (broker, account_number, broker_number, account_nickname)
                VALUES (?, ?, ?, ?)
                """,
                (broker, account_number, broker_number, account_nickname),
            )
            conn.commit()
            account_id = cursor.lastrowid
            logging.info(f"New account created with ID: {account_id}.")
            return account_id
        except sqlite3.Error as e:
            logging.error(f"Error retrieving or creating account_id: {e}")
            raise

def init_db():
    """Initializes the database tables with improvements."""
    logging.info("Initializing database with required tables.")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.executescript(
                """
                CREATE TABLE IF NOT EXISTS Accounts (
                    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    broker TEXT NOT NULL,
                    account_number TEXT NOT NULL,
                    account_nickname TEXT,
                    broker_number TEXT
                );

                CREATE TABLE IF NOT EXISTS HistoricalHoldings (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    quantity REAL NOT NULL CHECK (quantity >= 0),
                    average_price REAL NOT NULL CHECK (average_price >= 0),
                    FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
                );

                CREATE TABLE IF NOT EXISTS OrderHistory (
                    order_id TEXT PRIMARY KEY,
                    account_id INTEGER,
                    broker TEXT NOT NULL,
                    broker_name TEXT NOT NULL,
                    broker_number TEXT,
                    account_number TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quantity REAL NOT NULL CHECK (quantity >= 0),
                    price REAL NOT NULL CHECK (price >= 0),
                    total_value REAL NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT (DATETIME('now')),
                    FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
                );

                CREATE TABLE IF NOT EXISTS HoldingsLive (
                    holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER,
                    ticker TEXT NOT NULL,
                    quantity REAL NOT NULL CHECK (quantity >= 0),
                    average_price REAL NOT NULL CHECK (average_price >= 0),
                    timestamp TEXT NOT NULL DEFAULT (DATETIME('now')),
                    FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
                );
                """
            )
            conn.commit()
            logging.info("Database tables initialized successfully.")
        except sqlite3.Error as e:
            logging.error(f"Error initializing database tables: {e}")
            raise

def update_holdings_live(broker, broker_number, account_number, ticker, quantity, price):
    """Updates or inserts a holding into HoldingsLive."""
    logging.info(f"Updating holdings for ticker {ticker}, broker {broker}, account {account_number}.")
    account_id = get_or_create_account_id(broker, broker_number, account_number)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            # Insert the new holding
            cursor.execute(
                """
                INSERT INTO HoldingsLive (account_id, ticker, quantity, average_price, timestamp)
                VALUES (?, ?, ?, ?, DATETIME('now'))
                """,
                (account_id, ticker, quantity, price),
            )

            # Keep only the latest two entries per day
            cursor.execute(
                """
                DELETE FROM HoldingsLive
                WHERE rowid NOT IN (
                    SELECT rowid
                    FROM HoldingsLive
                    WHERE account_id = ? AND ticker = ? AND DATE(timestamp) = DATE('now')
                    ORDER BY timestamp DESC
                    LIMIT 2
                )
                """,
                (account_id, ticker),
            )
            conn.commit()
            logging.info(f"Holdings updated successfully for ticker {ticker}, account {account_id}.")
        except sqlite3.Error as e:
            logging.error(f"Error updating holdings: {e}")
            raise

def update_historical_holdings():
    """Updates HistoricalHoldings by averaging daily data from HoldingsLive."""
    logging.info("Updating historical holdings based on live data.")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO HistoricalHoldings (account_id, ticker, date, quantity, average_price)
                SELECT account_id, ticker, DATE(timestamp), AVG(quantity), AVG(average_price)
                FROM HoldingsLive
                WHERE DATE(timestamp) = DATE('now', '-1 day')
                GROUP BY account_id, ticker, DATE(timestamp)
                """
            )
            conn.commit()
            logging.info("Historical holdings updated successfully.")
        except sqlite3.Error as e:
            logging.error(f"Error updating historical holdings: {e}")
            raise


def validate_order_data(order_data):
    required_fields = [
        "order_id", "account_id", "broker", "broker_name", "broker_number",
        "account_number", "ticker", "date", "action", "quantity", "price", "total_value"
    ]
    for field in required_fields:
        if field not in order_data:
            raise ValueError(f"Missing required field in order_data: {field}")

import logging
import sqlite3
import time
import uuid


def insert_order_history(order_data):
    """
    Inserts a logged order into the OrderHistory table.

    Expected input fields (via ORDERS_HEADERS):
      - 'Broker Name'
      - 'Broker Number'
      - 'Account Number'
      - 'Order Type'
      - 'Stock'
      - 'Quantity'
      - 'Price'
      - 'Date'
      - 'Timestamp'
    
    This function:
      1. Maps these fields into the columns we use internally
      2. Generates order_id and account_id if missing
      3. Validates the final data
      4. Inserts into the OrderHistory table
    """

    logging.info("Attempting to insert order into OrderHistory.")

    # ------------------------------------------------------
    # 1) Map user-supplied fields to internal DB fields
    # ------------------------------------------------------
    # Convert your "Broker Name" etc. to the schema's expected keys
    mapped_order = {}
    mapped_order["broker_name"]     = order_data.get("Broker Name", "")
    mapped_order["broker_number"]   = order_data.get("Broker Number", "")
    mapped_order["account_number"]  = order_data.get("Account Number", "")
    mapped_order["action"]          = order_data.get("Order Type", "")   # e.g. buy/sell
    mapped_order["ticker"]          = order_data.get("Stock", "")
    mapped_order["quantity"]        = float(order_data.get("Quantity", 0))
    mapped_order["price"]           = float(order_data.get("Price", 0.0))
    mapped_order["date"]            = order_data.get("Date", "")
    mapped_order["timestamp"]       = order_data.get("Timestamp", "")  # if you need it
    # The database code references "broker" as well, so either set a default or combine:
    mapped_order["broker"]          = mapped_order["broker_name"] or "Unknown Broker"

    # If you'd like "total_value" in the DB, compute it automatically if not given:
    mapped_order["total_value"] = mapped_order["quantity"] * mapped_order["price"]

    # ------------------------------------------------------
    # 2) Generate or reuse order_id, account_id
    # ------------------------------------------------------
    # If we also are storing in the DB:
    mapped_order["order_id"] = order_data.get("order_id") or str(uuid.uuid4())

    # get_or_create_account_id depends on your code. Provide defaults if missing:
    mapped_order["account_id"] = order_data.get("account_id")
    if not mapped_order["account_id"]:
        broker = mapped_order["broker"]
        broker_num = mapped_order["broker_number"]
        acct_num = mapped_order["account_number"]
        mapped_order["account_id"] = get_or_create_account_id(
            broker, broker_num, acct_num, "Account Not Mapped"
        )

    # ------------------------------------------------------
    # 3) Validate order data
    # ------------------------------------------------------
    try:
        validate_order_data(mapped_order)
    except ValueError as ve:
        logging.error(f"Validation error: {ve}")
        raise

    # ------------------------------------------------------
    # 4) Insert into OrderHistory table
    # ------------------------------------------------------
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            logging.debug(f"Inserting order: {mapped_order}")
            cursor.execute(
                """
                INSERT INTO OrderHistory (
                    order_id,
                    account_id,
                    broker,
                    broker_name,
                    broker_number,
                    account_number,
                    ticker,
                    date,
                    action,
                    quantity,
                    price,
                    total_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mapped_order["order_id"],
                    mapped_order["account_id"],
                    mapped_order["broker"],
                    mapped_order["broker_name"],
                    mapped_order["broker_number"],
                    mapped_order["account_number"],
                    mapped_order["ticker"],
                    mapped_order["date"],
                    mapped_order["action"],
                    mapped_order["quantity"],
                    mapped_order["price"],
                    mapped_order["total_value"],
                ),
            )
            conn.commit()
        logging.info(
            f"Order inserted successfully for ticker: {mapped_order['ticker']} "
            f"(Order ID: {mapped_order['order_id']})."
        )
    except sqlite3.Error as e:
        logging.error(f"Error inserting order into OrderHistory: {e}")
        raise

'''
def insert_order_history(order_data):
    """Inserts a logged order into the OrderHistory table."""
    logging.info("Attempting to insert order into OrderHistory.")
    try:

        if "order_id" not in order_data or not order_data["order_id"]:
            order_data["order_id"] = str(uuid.uuid4())
            logging.debug(f"Generated order_id: {order_data['order_id']}")

        if "account_id" not in order_data or not order_data["account_id"]:
            broker = order_data["broker_name"]
            broker_number = order_data["broker_number"]
            account_number = order_data["account_number"]
            account_nickname = "Account Not Mapped"

            order_data["account_id"] = get_or_create_account_id(broker, broker_number, account_number, account_nickname)
        order_id = order_data["order_id"]
        account_id = order_data["account_id"]
        logging.info(f"Saving order with saved or generated OrderNo. {order_id} AccountNo. {account_id}")

        validate_order_data(order_data)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            logging.debug(f"Inserting order: {order_data}")
            cursor.execute(
                """
                INSERT INTO OrderHistory (
                    order_id, account_id, broker, broker_name, broker_number,
                    account_number, ticker, date, action, quantity, price, total_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_data["order_id"], order_data["account_id"], order_data["broker"],
                    order_data["broker_name"], order_data["broker_number"], order_data["account_number"],
                    order_data["ticker"], order_data["date"], order_data["action"],
                    order_data["quantity"], order_data["price"], order_data["total_value"]
                ),
            )
            conn.commit()
            logging.info(f"Order inserted successfully for ticker: {order_data['ticker']}.")
    except ValueError as ve:
        logging.error(f"Validation error: {ve}")
        raise
    except sqlite3.Error as e:
        logging.error(f"Error inserting order into OrderHistory: {e}")
        raise
'''

def bot_query_database(table_name, filters=None, order_by=None, limit=10):
    """Modular query function that handles errors and provides helpful feedback."""
    logging.info(f"Querying table {table_name} with filters: {filters}, order_by: {order_by}, limit: {limit}.")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            # Validate table name
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            valid_tables = [row[0] for row in cursor.fetchall()]
            if table_name not in valid_tables:
                logging.error(f"Invalid table: {table_name}. Available tables: {valid_tables}")
                return {"error": f"Invalid table name. Available tables: {valid_tables}"}

            # Fetch column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]

            # Construct query
            query = f"SELECT * FROM {table_name}"
            params = []

            if filters:
                conditions = []
                for key, value in filters.items():
                    if key in columns:
                        conditions.append(f"{key} = ?")
                        params.append(value)
                    else:
                        logging.warning(f"Invalid filter column: {key}. Available columns: {columns}")
                        return {"error": f"Invalid filter column: {key}. Available columns: {columns}"}
                query += " WHERE " + " AND ".join(conditions)

            if order_by and order_by in columns:
                query += f" ORDER BY {order_by}"

            if limit:
                query += f" LIMIT {limit}"

            logging.debug(f"Executing query: {query} with params: {params}")
            cursor.execute(query, params)
            rows = cursor.fetchall()
            logging.info(f"Query executed successfully. Retrieved {len(rows)} rows.")
            return {"data": rows, "columns": columns}
        except sqlite3.Error as e:
            logging.error(f"Database query error: {e}")
            return {"error": str(e)}
