import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta

from utils.config_utils import (
    ACCOUNT_MAPPING,
    SELL_FILE,
    SQL_DATABASE,
    get_account_nickname_or_default,
    SQL_LOGGING_ENABLED,
    WATCH_FILE,
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
            INSERT INTO account_mappings (
                broker,
                broker_number,
                account_number,
                account_nickname,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
            ON CONFLICT(broker, broker_number, account_number)
            DO UPDATE SET
                account_nickname = excluded.account_nickname,
                updated_at = DATETIME('now')
            """,
            (broker, broker_number, account_number, account_nickname),
        )

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
        else:
            cursor.execute(
                """
                INSERT INTO Accounts (broker, account_number, broker_number, account_nickname)
                VALUES (?, ?, ?, ?)
                """,
                (broker, account_number, broker_number, account_nickname),
            )
        conn.commit()
        logger.info(
            "Upserted SQL account nickname for %s/%s/%s.",
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
                        SELECT account_nickname
                        FROM account_mappings
                        WHERE broker = ? AND broker_number = ? AND account_number = ?
                        """,
                        (broker, broker_number, account_number),
                    )
                    row = cursor.fetchone()
                    if row:
                        if row[0] != nickname:
                            cursor.execute(
                                """
                                UPDATE account_mappings
                                SET account_nickname = ?, updated_at = DATETIME('now')
                                WHERE broker = ? AND broker_number = ? AND account_number = ?
                                """,
                                (nickname, broker, broker_number, account_number),
                            )
                            results["updated"] += 1
                    else:
                        cursor.execute(
                            """
                            INSERT INTO account_mappings (
                                broker,
                                broker_number,
                                account_number,
                                account_nickname,
                                created_at,
                                updated_at
                            )
                            VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
                            """,
                            (broker, broker_number, account_number, nickname),
                        )
                        results["added"] += 1

                    cursor.execute(
                        """
                        SELECT account_id, account_nickname
                        FROM Accounts
                        WHERE broker = ? AND broker_number = ? AND account_number = ?
                        """,
                        (broker, broker_number, account_number),
                    )
                    account_row = cursor.fetchone()
                    if account_row:
                        if account_row[1] != nickname:
                            cursor.execute(
                                """
                                UPDATE Accounts
                                SET account_nickname = ?
                                WHERE account_id = ?
                                """,
                                (nickname, account_row[0]),
                            )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO Accounts (broker, account_number, broker_number, account_nickname)
                            VALUES (?, ?, ?, ?)
                            """,
                            (broker, account_number, broker_number, nickname),
                        )

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
        cursor.execute("UPDATE account_mappings SET account_nickname = NULL")
        cleared = cursor.rowcount
        cursor.execute("UPDATE Accounts SET account_nickname = NULL")
        conn.commit()
        logger.info("Cleared account nicknames in SQL storage.")
        return cleared


def fetch_account_mappings() -> dict[str, dict[str, dict[str, str]]]:
    """Return account mappings stored in SQL.

    Returns:
        Nested mapping ``{broker: {broker_number: {account_number: nickname}}}``.
    """

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; returning empty account mappings.")
        return {}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT broker, broker_number, account_number, account_nickname
                FROM account_mappings
                ORDER BY broker, broker_number, account_number
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading account mappings: %s", exc)
            return {}

    mappings: dict[str, dict[str, dict[str, str]]] = {}
    for broker, broker_number, account_number, nickname in rows:
        if nickname is None:
            continue
        mappings.setdefault(broker, {}).setdefault(str(broker_number), {})[
            str(account_number)
        ] = nickname

    return mappings


def fetch_account_nickname(
    broker: str, broker_number: str, account_number: str
) -> str | None:
    """Return the nickname for an account from SQL."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; account nickname lookup skipped.")
        return None

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT account_nickname
                FROM account_mappings
                WHERE broker = ? AND broker_number = ? AND account_number = ?
                """,
                (broker, broker_number, account_number),
            )
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            logger.error("Failed reading account nickname: %s", exc)
            return None
    return row[0] if row else None


def fetch_account_labels() -> list[dict[str, str]]:
    """Return account IDs and nicknames from the Accounts table."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; account label lookup skipped.")
        return []

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT account_id, account_nickname
                FROM Accounts
                WHERE account_nickname IS NOT NULL
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading account labels: %s", exc)
            return []

    return [
        {"account_id": row[0], "account_nickname": row[1]} for row in rows if row[1]
    ]


def has_account_mappings() -> bool:
    """Return ``True`` when SQL has at least one account mapping row."""

    if not SQL_LOGGING_ENABLED:
        return False

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(1) FROM account_mappings")
            count = cursor.fetchone()[0]
        except sqlite3.Error as exc:
            logger.error("Failed checking account mappings: %s", exc)
            return False
    return count > 0


def _parse_metadata(metadata: str | None) -> dict:
    if not metadata:
        return {}
    try:
        return json.loads(metadata)
    except json.JSONDecodeError:
        logger.warning("Failed to parse metadata JSON; returning empty dict.")
        return {}


def _serialize_metadata(metadata: dict | None) -> str:
    return json.dumps(metadata or {}, ensure_ascii=False)


def fetch_watchlist_entries() -> dict[str, dict[str, str]]:
    """Return watchlist entries keyed by ticker."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; watchlist lookup skipped.")
        return {}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT ticker, split_date, split_ratio, metadata
                FROM watchlist
                ORDER BY ticker
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading watchlist: %s", exc)
            return {}

    watchlist: dict[str, dict[str, str]] = {}
    for ticker, split_date, split_ratio, metadata in rows:
        entry = {
            "split_date": split_date,
            "split_ratio": split_ratio or "N/A",
        }
        entry.update(_parse_metadata(metadata))
        watchlist[ticker.upper()] = entry

    return watchlist


def upsert_watchlist_entry(
    ticker: str,
    split_date: str,
    split_ratio: str,
    metadata: dict | None = None,
) -> bool:
    """Insert or update a watchlist entry."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; watchlist upsert skipped.")
        return False

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO watchlist (
                ticker,
                split_date,
                split_ratio,
                metadata,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
            ON CONFLICT(ticker)
            DO UPDATE SET
                split_date = excluded.split_date,
                split_ratio = excluded.split_ratio,
                metadata = excluded.metadata,
                updated_at = DATETIME('now')
            """,
            (ticker.upper(), split_date, split_ratio, _serialize_metadata(metadata)),
        )
        conn.commit()
    return True


def delete_watchlist_entry(ticker: str) -> bool:
    """Remove a watchlist entry by ticker."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; watchlist delete skipped.")
        return False

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
        return cursor.rowcount > 0


def fetch_sell_list_entries() -> dict[str, dict[str, str]]:
    """Return sell list entries keyed by ticker."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; sell list lookup skipped.")
        return {}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT ticker, split_date, split_ratio, metadata
                FROM sell_list
                ORDER BY ticker
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading sell list: %s", exc)
            return {}

    sell_list: dict[str, dict[str, str]] = {}
    for ticker, split_date, split_ratio, metadata in rows:
        entry = _parse_metadata(metadata)
        if split_date:
            entry.setdefault("split_date", split_date)
        if split_ratio:
            entry.setdefault("split_ratio", split_ratio)
        sell_list[ticker.upper()] = entry

    return sell_list


def upsert_sell_list_entry(
    ticker: str,
    split_date: str | None = None,
    split_ratio: str | None = None,
    metadata: dict | None = None,
) -> bool:
    """Insert or update a sell list entry."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; sell list upsert skipped.")
        return False

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sell_list (
                ticker,
                split_date,
                split_ratio,
                metadata,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
            ON CONFLICT(ticker)
            DO UPDATE SET
                split_date = excluded.split_date,
                split_ratio = excluded.split_ratio,
                metadata = excluded.metadata,
                updated_at = DATETIME('now')
            """,
            (ticker.upper(), split_date, split_ratio, _serialize_metadata(metadata)),
        )
        conn.commit()
    return True


def delete_sell_list_entry(ticker: str) -> bool:
    """Remove a sell list entry by ticker."""

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; sell list delete skipped.")
        return False

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sell_list WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
        return cursor.rowcount > 0


def fetch_watchlist_entry(ticker: str) -> dict[str, str] | None:
    """Return a single watchlist entry by ticker.

    Args:
        ticker: Symbol to fetch.

    Returns:
        Watchlist payload when present, otherwise ``None``.
    """

    return fetch_watchlist_entries().get(ticker.upper())


def replace_watchlist_entries(entries: dict[str, dict[str, str]]) -> int:
    """Replace the entire watchlist table with ``entries``.

    Args:
        entries: Mapping keyed by ticker containing ``split_date`` and optional
            ``split_ratio`` plus metadata fields.

    Returns:
        Number of rows written.
    """

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; watchlist replace skipped.")
        return 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist")
        for ticker, data in entries.items():
            payload = data if isinstance(data, dict) else {}
            metadata = {
                key: value
                for key, value in payload.items()
                if key not in {"split_date", "split_ratio"}
            }
            cursor.execute(
                """
                INSERT INTO watchlist (
                    ticker,
                    split_date,
                    split_ratio,
                    metadata,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
                """,
                (
                    ticker.upper(),
                    payload.get("split_date"),
                    payload.get("split_ratio", "N/A"),
                    _serialize_metadata(metadata or None),
                ),
            )
        conn.commit()
        return len(entries)


def fetch_sell_list_entry(ticker: str) -> dict[str, str] | None:
    """Return a single sell list entry by ticker."""

    return fetch_sell_list_entries().get(ticker.upper())


def replace_sell_list_entries(entries: dict[str, dict[str, str]]) -> int:
    """Replace the entire sell list table with ``entries``.

    Args:
        entries: Mapping keyed by ticker that may include split metadata and
            scheduling fields.

    Returns:
        Number of rows written.
    """

    if not SQL_LOGGING_ENABLED:
        logger.warning("SQL logging disabled; sell list replace skipped.")
        return 0

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sell_list")
        for ticker, data in entries.items():
            payload = data if isinstance(data, dict) else {}
            cursor.execute(
                """
                INSERT INTO sell_list (
                    ticker,
                    split_date,
                    split_ratio,
                    metadata,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
                """,
                (
                    ticker.upper(),
                    payload.get("split_date"),
                    payload.get("split_ratio"),
                    _serialize_metadata(payload),
                ),
            )
        conn.commit()
        return len(entries)


def _load_legacy_json(path: os.PathLike) -> dict:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            logger.warning("Legacy JSON %s is not a dict; skipping.", path)
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed reading legacy JSON %s: %s", path, exc)
        return {}


def migrate_legacy_json_data(remove_legacy_files: bool = False) -> dict[str, int]:
    """Migrate legacy JSON mappings/watchlists into SQL tables.

    The migration is idempotent for populated SQL tables and only imports a
    legacy dataset when the corresponding table is empty.

    Args:
        remove_legacy_files: When ``True``, rename successfully imported legacy
            JSON files to ``*.migrated`` so they are no longer consumed.

    Returns:
        Mapping of migrated row counts for each dataset.
    """

    results = {"account_mappings": 0, "watchlist": 0, "sell_list": 0}
    if not SQL_LOGGING_ENABLED:
        logger.info("SQL logging disabled; skipping legacy JSON migration.")
        return results

    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(1) FROM account_mappings")
            has_account_rows = cursor.fetchone()[0] > 0
            cursor.execute("SELECT COUNT(1) FROM watchlist")
            has_watch_rows = cursor.fetchone()[0] > 0
            cursor.execute("SELECT COUNT(1) FROM sell_list")
            has_sell_rows = cursor.fetchone()[0] > 0
        except sqlite3.Error as exc:
            logger.error("Failed checking legacy migration state: %s", exc)
            return results

    if not has_account_rows:
        legacy_mappings = _load_legacy_json(ACCOUNT_MAPPING)
        if legacy_mappings:
            sync_results = sync_account_mappings(legacy_mappings)
            results["account_mappings"] = (
                sync_results["added"] + sync_results["updated"]
            )

    if not has_watch_rows:
        legacy_watch = _load_legacy_json(WATCH_FILE)
        for ticker, data in legacy_watch.items():
            if isinstance(data, dict):
                split_date = data.get("split_date")
                split_ratio = data.get("split_ratio", "N/A")
            else:
                split_date = None
                split_ratio = "N/A"
            if split_date:
                upsert_watchlist_entry(
                    ticker=ticker,
                    split_date=split_date,
                    split_ratio=split_ratio,
                    metadata=None,
                )
                results["watchlist"] += 1

    if not has_sell_rows:
        legacy_sell = _load_legacy_json(SELL_FILE)
        for ticker, data in legacy_sell.items():
            metadata = data if isinstance(data, dict) else {}
            upsert_sell_list_entry(
                ticker=ticker,
                split_date=metadata.get("split_date"),
                split_ratio=metadata.get("split_ratio"),
                metadata=metadata,
            )
            results["sell_list"] += 1

    if any(results.values()):
        logger.info(
            "Legacy JSON migration complete. account_mappings=%s watchlist=%s sell_list=%s",
            results["account_mappings"],
            results["watchlist"],
            results["sell_list"],
        )
        if remove_legacy_files:
            for path in (ACCOUNT_MAPPING, WATCH_FILE, SELL_FILE):
                try:
                    if os.path.exists(path):
                        os.replace(path, f"{path}.migrated")
                        logger.info("Archived legacy JSON file %s.migrated", path)
                except OSError as exc:
                    logger.warning(
                        "Failed to archive legacy JSON file %s: %s", path, exc
                    )
    return results


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

                CREATE TABLE IF NOT EXISTS account_mappings (
                    broker TEXT NOT NULL,
                    broker_number TEXT NOT NULL,
                    account_number TEXT NOT NULL,
                    account_nickname TEXT,
                    created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
                    updated_at TEXT NOT NULL DEFAULT (DATETIME('now')),
                    PRIMARY KEY (broker, broker_number, account_number)
                );

                CREATE TABLE IF NOT EXISTS watchlist (
                    ticker TEXT PRIMARY KEY,
                    split_date TEXT,
                    split_ratio TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
                    updated_at TEXT NOT NULL DEFAULT (DATETIME('now'))
                );

                CREATE TABLE IF NOT EXISTS sell_list (
                    ticker TEXT PRIMARY KEY,
                    split_date TEXT,
                    split_ratio TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
                    updated_at TEXT NOT NULL DEFAULT (DATETIME('now'))
                );
                """
            )
            conn.commit()
            logger.info("Database tables initialized successfully.")
            migrate_legacy_json_data()
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
