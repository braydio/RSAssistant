import logging
import os
import sqlite3
import uuid
from datetime import datetime
import asyncio

from utils.config_utils import SQL_DATABASE_DB_V1, load_config, setup_logging

# Config and setup
config = load_config()
setup_logging()

PRIMARY_DB_FILE = SQL_DATABASE_DB_V1 # config.get("paths", {}).get("database", "volumes/db/reverse_splits.db")

# Database connection helper
def get_db_connection():
    """Helper function to get a database connection."""
    conn = sqlite3.connect(PRIMARY_DB_FILE, timeout=30)  # Extend timeout to avoid lock errors
    conn.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode for better concurrency
    return conn

def get_or_create_account_id(broker, broker_number, account_number, account_nickname="AccountNotMapped"):
    """
    Retrieves the account_id for a given broker and account number. If it doesn't exist, it creates a new entry.
    """
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
            return cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"Error retrieving or creating account_id: {e}")
            raise


def init_db():
    """Initializes the database tables with improvements."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
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

            CREATE INDEX IF NOT EXISTS idx_ticker ON HistoricalHoldings(ticker);
            CREATE INDEX IF NOT EXISTS idx_account_id ON OrderHistory(account_id);
            CREATE INDEX IF NOT EXISTS idx_timestamp ON HistoricalHoldings(date);
            """
        )
        conn.commit()
        logging.info("Database initialized with enhancements.")


def update_holdings_live(broker, broker_number, account_number, ticker, quantity, average_price):
    """Updates or inserts a holding into HoldingsLive, keeping only the latest two entries per day."""
    account_id = get_or_create_account_id(broker, broker_number, account_number)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert the new holding
        cursor.execute(
            """
            INSERT INTO HoldingsLive (account_id, ticker, quantity, average_price, timestamp)
            VALUES (?, ?, ?, ?, DATETIME('now'))
            """,
            (account_id, ticker, quantity, average_price),
        )

        # Delete older entries beyond the two most recent for the day
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
        logging.info(f"Updated HoldingsLive for ticker {ticker}, account {account_id}.")


# Update historical holdings daily

def update_historical_holdings():
    """Updates HistoricalHoldings by averaging daily data from HoldingsLive."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

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
        logging.info("Updated HistoricalHoldings from HoldingsLive.")

# Insert an order into OrderHistory

def insert_order_history(order_data):
    """Inserts a logged order into the OrderHistory table."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
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
        logging.info(f"Order logged for ticker: {order_data['ticker']} on {order_data['date']}")

# Enhanced query functionality

def bot_query_database(table_name, filters=None, order_by=None, limit=10):
    """Modular query function that handles errors and provides helpful feedback."""
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

            # Execute query
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return {"data": rows, "columns": columns}

        except sqlite3.Error as e:
            logging.error(f"Database query error: {e}")
            return {"error": str(e)}
