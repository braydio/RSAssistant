"""Small, explicit SQLite schema migrations using ``PRAGMA user_version``."""

import sqlite3
import json
import logging
import math
from collections.abc import Callable

LATEST_SCHEMA_VERSION = 8

logger = logging.getLogger(__name__)


def _migration_1(conn: sqlite3.Connection) -> None:
    """Create the legacy-compatible baseline schema."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS Accounts (
            account_id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_number TEXT NOT NULL,
            account_nickname TEXT,
            broker_number TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            updated_at TEXT NOT NULL DEFAULT (DATETIME('now'))
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
            order_id TEXT PRIMARY KEY, account_id INTEGER,
            broker TEXT NOT NULL, broker_name TEXT NOT NULL,
            broker_number TEXT, account_number TEXT NOT NULL,
            ticker TEXT NOT NULL, date TEXT NOT NULL, action TEXT NOT NULL,
            quantity REAL NOT NULL CHECK (quantity >= 0),
            price REAL NOT NULL CHECK (price >= 0), total_value REAL NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (DATETIME('now')),
            FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
        );
        CREATE TABLE IF NOT EXISTS HoldingsLive (
            holding_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER,
            ticker TEXT NOT NULL, quantity REAL NOT NULL CHECK (quantity >= 0),
            average_price REAL NOT NULL CHECK (average_price >= 0),
            timestamp TEXT NOT NULL DEFAULT (DATETIME('now')),
            FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
        );
        CREATE TABLE IF NOT EXISTS account_mappings (
            broker TEXT NOT NULL, broker_number TEXT NOT NULL,
            account_number TEXT NOT NULL, account_nickname TEXT,
            created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            updated_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            PRIMARY KEY (broker, broker_number, account_number)
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY, split_date TEXT, split_ratio TEXT,
            metadata TEXT, created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            updated_at TEXT NOT NULL DEFAULT (DATETIME('now'))
        );
        CREATE TABLE IF NOT EXISTS sell_list (
            ticker TEXT PRIMARY KEY, split_date TEXT, split_ratio TEXT,
            metadata TEXT, created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
            updated_at TEXT NOT NULL DEFAULT (DATETIME('now'))
        );
        CREATE TABLE IF NOT EXISTS ReverseSplitLog (
            ticker TEXT NOT NULL, split_ratio TEXT, split_date TEXT NOT NULL,
            ingestion_timestamp TEXT NOT NULL DEFAULT (DATETIME('now')), source TEXT
        );
        CREATE TABLE IF NOT EXISTS ReverseSplitAccountEntries (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL,
            ticker TEXT NOT NULL, entry_type TEXT NOT NULL,
            price REAL NOT NULL CHECK (price >= 0),
            timestamp TEXT NOT NULL DEFAULT (DATETIME('now')), source TEXT,
            FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
        );
        """
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _migration_2(conn: sqlite3.Connection) -> None:
    """Make accounts and daily holdings unique without losing references."""
    account_columns = _columns(conn, "Accounts")
    if "created_at" not in account_columns:
        conn.execute("ALTER TABLE Accounts ADD COLUMN created_at TEXT")
        conn.execute("UPDATE Accounts SET created_at = DATETIME('now')")
    if "updated_at" not in account_columns:
        conn.execute("ALTER TABLE Accounts ADD COLUMN updated_at TEXT")
        conn.execute("UPDATE Accounts SET updated_at = DATETIME('now')")
    conn.execute("UPDATE Accounts SET broker_number = '' WHERE broker_number IS NULL")

    groups = conn.execute(
        """SELECT broker, broker_number, account_number, MIN(account_id)
           FROM Accounts GROUP BY broker, broker_number, account_number
           HAVING COUNT(*) > 1"""
    ).fetchall()
    for broker, broker_number, account_number, canonical_id in groups:
        duplicates = conn.execute(
            """SELECT account_id FROM Accounts
               WHERE broker=? AND broker_number=? AND account_number=?
                 AND account_id<>?""",
            (broker, broker_number, account_number, canonical_id),
        ).fetchall()
        for (duplicate_id,) in duplicates:
            for table in ("HistoricalHoldings", "HoldingsLive", "OrderHistory",
                          "ReverseSplitAccountEntries"):
                conn.execute(f"UPDATE {table} SET account_id=? WHERE account_id=?",
                             (canonical_id, duplicate_id))
            conn.execute(
                """UPDATE Accounts SET account_nickname=COALESCE(
                       account_nickname,
                       (SELECT account_nickname FROM Accounts WHERE account_id=?))
                   WHERE account_id=?""",
                (duplicate_id, canonical_id),
            )
            conn.execute("DELETE FROM Accounts WHERE account_id=?", (duplicate_id,))

    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_accounts_identity
                    ON Accounts(broker, broker_number, account_number)""")
    conn.execute(
        """DELETE FROM HistoricalHoldings WHERE history_id NOT IN (
               SELECT MAX(history_id) FROM HistoricalHoldings
               GROUP BY account_id, ticker, date)"""
    )
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_historical_holdings_daily
                    ON HistoricalHoldings(account_id, ticker, date)""")
    conn.execute(
        """INSERT INTO Accounts (
               broker, broker_number, account_number, account_nickname,
               created_at, updated_at)
           SELECT broker, broker_number, account_number, account_nickname,
                  created_at, updated_at FROM account_mappings
           WHERE account_nickname IS NOT NULL
           ON CONFLICT(broker, broker_number, account_number) DO UPDATE SET
               account_nickname=excluded.account_nickname,
               updated_at=excluded.updated_at"""
    )


def _migration_3(conn: sqlite3.Connection) -> None:
    """Add indexes used by history and reverse-split query paths."""
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_historical_holdings_account_ticker_date
        ON HistoricalHoldings(account_id, ticker, date);
        CREATE INDEX IF NOT EXISTS idx_holdings_live_timestamp ON HoldingsLive(timestamp);
        CREATE INDEX IF NOT EXISTS idx_reverse_split_log_ticker_time
        ON ReverseSplitLog(ticker, ingestion_timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_reverse_split_entries_account_ticker_time
        ON ReverseSplitAccountEntries(account_id, ticker, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_order_history_account_date
        ON OrderHistory(account_id, date);
        CREATE INDEX IF NOT EXISTS idx_order_history_ticker_date
        ON OrderHistory(ticker, date);
        """
    )


def _migration_4(conn: sqlite3.Connection) -> None:
    """Create durable storage for scheduled order queue entries."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS order_queue (
               order_id TEXT PRIMARY KEY,
               order_data TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
               updated_at TEXT NOT NULL DEFAULT (DATETIME('now'))
           )"""
    )


def _migration_5(conn: sqlite3.Connection) -> None:
    """Normalize scheduled orders and create the sent-order audit table."""
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS scheduled_orders (
            order_id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            ticker TEXT NOT NULL,
            quantity REAL NOT NULL,
            broker TEXT NOT NULL,
            scheduled_at TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_orders_scheduled_at "
        "ON scheduled_orders(scheduled_at)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS rsa_order_send_log (
            send_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sent_at TEXT NOT NULL,
            command TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity REAL NOT NULL,
            broker TEXT NOT NULL,
            legacy_key TEXT UNIQUE
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rsa_order_send_log_sent_at "
        "ON rsa_order_send_log(sent_at, send_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_rsa_order_send_log_ticker_sent_at "
        "ON rsa_order_send_log(ticker, sent_at, send_id)"
    )

    has_legacy_queue = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='order_queue'"
    ).fetchone()
    if not has_legacy_queue:
        return

    rows = conn.execute(
        "SELECT order_id, order_data, created_at, updated_at FROM order_queue"
    ).fetchall()
    for order_id, raw_data, created_at, updated_at in rows:
        try:
            data = json.loads(raw_data)
            if not isinstance(data, dict):
                raise ValueError("order data is not an object")
            action = str(data["action"])
            ticker = str(data["ticker"]).upper()
            quantity = float(data["quantity"])
            broker = str(data["broker"])
            scheduled_at = str(data["time"])
            state = str(data.get("status", "pending")).lower()
            attempt_count = int(data.get("attempt_count", 0))
            last_error = data.get("last_error")
            metadata = {
                key: value
                for key, value in data.items()
                if key
                not in {
                    "action",
                    "ticker",
                    "quantity",
                    "broker",
                    "time",
                }
            }
            if not all((action.strip(), ticker.strip(), broker.strip(), scheduled_at.strip())):
                raise ValueError("queue entry has an empty required field")
            if not math.isfinite(quantity) or attempt_count < 0:
                raise ValueError("queue entry has invalid numeric fields")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Skipping malformed legacy SQL order %s: %s", order_id, exc)
            continue

        conn.execute(
            """INSERT OR IGNORE INTO scheduled_orders (
                   order_id, action, ticker, quantity, broker, scheduled_at,
                   state, attempt_count, last_error, metadata_json,
                   created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(order_id),
                action,
                ticker,
                quantity,
                broker,
                scheduled_at,
                state,
                attempt_count,
                last_error,
                json.dumps(metadata),
                created_at,
                updated_at,
            ),
        )

    conn.execute("DROP TABLE order_queue")


def _migration_6(conn: sqlite3.Connection) -> None:
    """Create normalized split monitor state tables."""
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS split_monitor (
               ticker TEXT PRIMARY KEY,
               split_date TEXT NOT NULL,
               status TEXT NOT NULL CHECK(status IN ('buying', 'selling')),
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )


def _migration_7(conn: sqlite3.Connection) -> None:
    """Create current holdings and staged refresh tables."""
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS holdings_current (
               account_id INTEGER NOT NULL,
               ticker TEXT NOT NULL,
               quantity REAL NOT NULL,
               price REAL NOT NULL,
               position_value REAL NOT NULL,
               account_total REAL,
               observed_at TEXT NOT NULL,
               source TEXT NOT NULL,
               PRIMARY KEY (account_id, ticker),
               FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
           )"""
    )


    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_holdings_current_ticker "
        "ON holdings_current(ticker)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_holdings_current_observed_at "
        "ON holdings_current(observed_at)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS holdings_refreshes (
               refresh_id TEXT PRIMARY KEY,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS holdings_refresh_staging (
               refresh_id TEXT NOT NULL,
               account_id INTEGER NOT NULL,
               ticker TEXT NOT NULL,
               quantity REAL NOT NULL,
               price REAL NOT NULL,
               position_value REAL NOT NULL,
               account_total REAL,
               observed_at TEXT NOT NULL,
               source TEXT NOT NULL,
               PRIMARY KEY (refresh_id, account_id, ticker),
               FOREIGN KEY (refresh_id) REFERENCES holdings_refreshes(refresh_id)
                   ON DELETE CASCADE,
               FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
           )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_holdings_refresh_staging_refresh "
        "ON holdings_refresh_staging(refresh_id)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS split_monitor_accounts (
               ticker TEXT NOT NULL,
               account_name TEXT NOT NULL,
               bought INTEGER NOT NULL DEFAULT 0,
               sold INTEGER NOT NULL DEFAULT 0,
               PRIMARY KEY (ticker, account_name),
               FOREIGN KEY (ticker) REFERENCES split_monitor(ticker)
                   ON DELETE CASCADE
           )"""
    )


def _migration_8(conn: sqlite3.Connection) -> None:
    """Record one-time imports from legacy operator-readable files."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS legacy_imports (
               source_key TEXT PRIMARY KEY,
               completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
               imported_rows INTEGER NOT NULL DEFAULT 0
           )"""
    )


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migration_1, 2: _migration_2, 3: _migration_3,
    4: _migration_4, 5: _migration_5, 6: _migration_6, 7: _migration_7,
    8: _migration_8,
}


def run_migrations(conn: sqlite3.Connection) -> int:
    """Upgrade ``conn`` transactionally and return its schema version."""
    conn.execute("PRAGMA journal_mode = WAL")
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    for version in range(current + 1, LATEST_SCHEMA_VERSION + 1):
        try:
            MIGRATIONS[version](conn)
            conn.execute(f"PRAGMA user_version = {version}")
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
    return LATEST_SCHEMA_VERSION
