import asyncio
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta

from utils.config_utils import (
    SQL_DATABASE,
    get_account_nickname_or_default,
    SQL_LOGGING_ENABLED,
)

logger = logging.getLogger(__name__)

SQL_DATABASE = SQL_DATABASE  # config.get("paths", {}).get("database", "volumes/db/reverse_splits.db")


# Database connection helper
def get_db_connection():
    """Return a database connection when SQL logging is enabled."""

    if not SQL_LOGGING_ENABLED:
        logger.debug("SQL logging disabled; database connection not created.")
        raise RuntimeError("SQL logging disabled")

    logger.debug("Attempting to establish a database connection.")
    try:
        conn = sqlite3.connect(
            SQL_DATABASE, timeout=30
        )  # Extend timeout to avoid lock errors
        conn.execute(
            "PRAGMA journal_mode=WAL;"
        )  # Enable WAL mode for better concurrency
        logger.debug("Database connection established successfully.")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error establishing database connection: {e}")
        raise


def get_or_create_account_id(
    broker, broker_number, account_number, account_nickname=None
):
    """
    Retrieve or create an account entry.

    Returns ``None`` when SQL logging is disabled. If ``account_nickname``
    is ``None`` the nickname is resolved using
    :func:`utils.config_utils.get_account_nickname_or_default`.
    """
    logger.info(
        f"Fetching or creating account ID for broker: {broker}, broker_number: {broker_number}, account_number: {account_number}."
    )

    if not SQL_LOGGING_ENABLED:
        logger.debug("SQL logging disabled; skipping account lookup.")
        return None

    if account_nickname is None:
        account_nickname = get_account_nickname_or_default(
            broker, broker_number, account_number
        )

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
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
                logger.debug(f"Account ID found: {result[0]}.")
                return result[0]

            cursor.execute(
                """
                INSERT INTO Accounts (broker, account_number, broker_number, account_nickname)
                VALUES (?, ?, ?, ?)
                """,
                (broker, account_number, broker_number, account_nickname),
            )
            conn.commit()
            account_id = cursor.lastrowid
            logger.info(f"New account created with ID: {account_id}.")
            return account_id
        except sqlite3.Error as e:
            logger.error(f"Error retrieving or creating account_id: {e}")
            raise


def upsert_account_mapping(
    broker: str, broker_number: str, account_number: str, account_nickname: str
) -> bool:
    """Insert or update account nickname mappings in SQL storage.

    Args:
        broker: Broker name for the account.
        broker_number: Broker group identifier.
        account_number: Account identifier.
        account_nickname: Friendly nickname to store.

    Returns:
        ``True`` when SQL storage was updated, ``False`` when SQL logging is
        disabled.
    """

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; account mapping not stored.")
        return False

    with get_db_connection() as conn:
        cursor = conn.cursor()
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
            cursor.execute(
                """
                UPDATE Accounts
                SET account_nickname = ?
                WHERE account_id = ?
                """,
                (account_nickname, result[0]),
            )
            conn.commit()
            logger.info(
                "Updated SQL account nickname for %s/%s/%s.",
                broker,
                broker_number,
                account_number,
            )
            return True

        cursor.execute(
            """
            INSERT INTO Accounts (broker, account_number, broker_number, account_nickname)
            VALUES (?, ?, ?, ?)
            """,
            (broker, account_number, broker_number, account_nickname),
        )
        conn.commit()
        logger.info(
            "Inserted SQL account nickname for %s/%s/%s.",
            broker,
            broker_number,
            account_number,
        )
        return True


def sync_account_mappings(mappings: dict) -> dict[str, int]:
    """Synchronize a JSON mapping dictionary into SQL storage.

    Args:
        mappings: Nested broker/group/account mapping structure.

    Returns:
        Dictionary with ``added`` and ``updated`` counts.
    """

    results = {"added": 0, "updated": 0}
    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; account mapping sync skipped.")
        return results

    with get_db_connection() as conn:
        cursor = conn.cursor()
        for broker, broker_groups in mappings.items():
            for broker_number, accounts in broker_groups.items():
                for account_number, nickname in accounts.items():
                    cursor.execute(
                        """
                        SELECT account_id, account_nickname
                        FROM Accounts
                        WHERE broker = ? AND broker_number = ? AND account_number = ?
                        """,
                        (broker, broker_number, account_number),
                    )
                    row = cursor.fetchone()
                    if row:
                        if row[1] != nickname:
                            cursor.execute(
                                """
                                UPDATE Accounts
                                SET account_nickname = ?
                                WHERE account_id = ?
                                """,
                                (nickname, row[0]),
                            )
                            results["updated"] += 1
                    else:
                        cursor.execute(
                            """
                            INSERT INTO Accounts (broker, account_number, broker_number, account_nickname)
                            VALUES (?, ?, ?, ?)
                            """,
                            (broker, account_number, broker_number, nickname),
                        )
                        results["added"] += 1

        conn.commit()

    logger.info(
        "Synced account mappings to SQL. Added=%s Updated=%s",
        results["added"],
        results["updated"],
    )
    return results


def clear_account_nicknames() -> int:
    """Clear stored account nicknames from SQL storage.

    Returns:
        Number of rows updated.
    """

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; account nickname clear skipped.")
        return 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Accounts SET account_nickname = NULL")
        conn.commit()
        logger.info("Cleared account nicknames in SQL storage.")
        return cursor.rowcount


def init_db():
    """Initialize database tables if SQL logging is enabled."""

    if not SQL_LOGGING_ENABLED:
        logger.info("SQL logging disabled; skipping database initialization.")
        return

    logger.info("Initializing database with required tables.")
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
            logger.info("Database tables initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"Error initializing database tables: {e}")
            raise


def update_holdings_live(
    broker, broker_number, account_number, ticker, quantity, price
):
    """Insert a holding into ``HoldingsLive`` when logging is enabled."""

    if not SQL_LOGGING_ENABLED:
        logger.info("SQL logging disabled; skipping holdings update.")
        return

    logger.info(
        f"Updating holdings for ticker {ticker}, broker {broker}, account {account_number}."
    )
    account_id = get_or_create_account_id(broker, broker_number, account_number)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO HoldingsLive (account_id, ticker, quantity, average_price, timestamp)
                VALUES (?, ?, ?, ?, DATETIME('now'))
                """,
                (account_id, ticker, quantity, price),
            )

            logger.info(
                f"Holdings updated successfully for ticker {ticker}, account {account_id}."
            )
        except sqlite3.Error as e:
            logger.error(f"Error updating holdings: {e}")
            raise


def update_historical_holdings():
    """Updates HistoricalHoldings by averaging daily data from HoldingsLive."""
    logger.info("Updating historical holdings based on live data.")
    # Calculate yesterday's date as a string in 'YYYY-MM-DD' format.
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            # Insert aggregated holdings for yesterday.
            cursor.execute(
                """
                INSERT INTO HistoricalHoldings (account_id, ticker, date, quantity, average_price)
                SELECT account_id,
                       ticker,
                       DATE(timestamp) AS date,
                       AVG(quantity) AS avg_quantity,
                       AVG(average_price) AS avg_price
                FROM HoldingsLive
                WHERE DATE(timestamp) = ?
                GROUP BY account_id, ticker, DATE(timestamp)
                """,
                (yesterday_date,),
            )
            conn.commit()
            logger.info("Historical holdings updated successfully.")
        except sqlite3.Error as e:
            logger.error(f"Error updating historical holdings: {e}")
            raise


def validate_order_data(order_data):
    required_fields = [
        "order_id",
        "account_id",
        "broker",
        "broker_name",
        "broker_number",
        "account_number",
        "ticker",
        "date",
        "action",
        "quantity",
        "price",
        "total_value",
    ]
    for field in required_fields:
        if field not in order_data:
            raise ValueError(f"Missing required field in order_data: {field}")


def insert_order_history(order_data):
    """
    Inserts a logged order into the ``OrderHistory`` table.

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

    logger.info("Attempting to insert order into OrderHistory.")
    mapped_order = {}
    mapped_order["broker_name"] = order_data.get("Broker Name", "")
    mapped_order["broker_number"] = order_data.get("Broker Number", "")
    mapped_order["account_number"] = order_data.get("Account Number", "")
    mapped_order["action"] = order_data.get("Order Type", "")  # e.g. buy/sell
    mapped_order["ticker"] = order_data.get("Stock", "")
    mapped_order["quantity"] = float(order_data.get("Quantity", 0))
    mapped_order["price"] = float(order_data.get("Price", 0.0))
    mapped_order["date"] = order_data.get("Date", "")
    mapped_order["timestamp"] = order_data.get("Timestamp", "")  # if you need it
    mapped_order["broker"] = mapped_order["broker_name"] or "Unknown Broker"
    mapped_order["total_value"] = mapped_order["quantity"] * mapped_order["price"]
    mapped_order["order_id"] = order_data.get("order_id") or str(uuid.uuid4())
    mapped_order["account_id"] = order_data.get("account_id")
    if not mapped_order["account_id"]:
        broker = mapped_order["broker"]
        broker_num = mapped_order["broker_number"]
        acct_num = mapped_order["account_number"]
        mapped_order["account_id"] = get_or_create_account_id(
            broker, broker_num, acct_num
        )

    try:
        validate_order_data(mapped_order)
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise

    # ------------------------------------------------------
    # 4) Insert into OrderHistory table
    # ------------------------------------------------------
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            logger.debug(f"Inserting order: {mapped_order}")
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
        logger.info(
            f"Order inserted successfully for ticker: {mapped_order['ticker']} "
            f"(Order ID: {mapped_order['order_id']})."
        )
    except sqlite3.Error as e:
        logger.error(f"Error inserting order into OrderHistory: {e}")
        raise


'''
def insert_order_history(order_data):
    """Inserts a logged order into the OrderHistory table."""
    logger.info("Attempting to insert order into OrderHistory.")
    try:

        if "order_id" not in order_data or not order_data["order_id"]:
            order_data["order_id"] = str(uuid.uuid4())
            logger.debug(f"Generated order_id: {order_data['order_id']}")

        if "account_id" not in order_data or not order_data["account_id"]:
            broker = order_data["broker_name"]
            broker_number = order_data["broker_number"]
            account_number = order_data["account_number"]
            account_nickname = get_account_nickname_or_default(
                broker, broker_number, account_number
            )

            order_data["account_id"] = get_or_create_account_id(broker, broker_number, account_number, account_nickname)
        order_id = order_data["order_id"]
        account_id = order_data["account_id"]
        logger.info(f"Saving order with saved or generated OrderNo. {order_id} AccountNo. {account_id}")

        validate_order_data(order_data)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            logger.debug(f"Inserting order: {order_data}")
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
            logger.info(f"Order inserted successfully for ticker: {order_data['ticker']}.")
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
        raise
    except sqlite3.Error as e:
        logger.error(f"Error inserting order into OrderHistory: {e}")
        raise
'''


def bot_query_database(table_name, filters=None, order_by=None, limit=10):
    """Query a table and return rows or an error message.

    Returns a descriptive error when SQL logging is disabled.
    """

    if not SQL_LOGGING_ENABLED:
        logger.info("SQL logging disabled; query aborted.")
        return {"error": "SQL logging disabled"}

    logger.info(
        f"Querying table {table_name} with filters: {filters}, order_by: {order_by}, limit: {limit}."
    )
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            # Validate table name
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            valid_tables = [row[0] for row in cursor.fetchall()]
            if table_name not in valid_tables:
                logger.error(
                    f"Invalid table: {table_name}. Available tables: {valid_tables}"
                )
                return {
                    "error": f"Invalid table name. Available tables: {valid_tables}"
                }

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
                        logger.warning(
                            f"Invalid filter column: {key}. Available columns: {columns}"
                        )
                        return {
                            "error": f"Invalid filter column: {key}. Available columns: {columns}"
                        }
                query += " WHERE " + " AND ".join(conditions)

            if order_by and order_by in columns:
                query += f" ORDER BY {order_by}"

            if limit:
                query += f" LIMIT {limit}"

            logger.debug(f"Executing query: {query} with params: {params}")
            cursor.execute(query, params)
            rows = cursor.fetchall()
            logger.info(f"Query executed successfully. Retrieved {len(rows)} rows.")
            return {"data": rows, "columns": columns}
        except sqlite3.Error as e:
            logger.error(f"Database query error: {e}")
            return {"error": str(e)}
