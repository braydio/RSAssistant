"""Small, explicit SQLite schema migrations using ``PRAGMA user_version``."""

import sqlite3
from collections.abc import Callable

LATEST_SCHEMA_VERSION = 4


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


MIGRATIONS: dict[int, Callable[[sqlite3.Connection], None]] = {
    1: _migration_1, 2: _migration_2, 3: _migration_3,
    4: _migration_4,
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
