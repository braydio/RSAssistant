"""Reverse-split event and account-entry persistence."""

from __future__ import annotations

import logging
from typing import Any

from rsassistant.persistence.db import connect_runtime_db
from utils.config_utils import SQL_DATABASE

logger = logging.getLogger(__name__)
DATABASE_PATH = SQL_DATABASE


def _get_db_connection(database=None):
    return connect_runtime_db(database or DATABASE_PATH)


def insert_reverse_split_log_entry(
    ticker: str,
    split_ratio: str | None,
    split_date: str,
    source: str,
    ingestion_timestamp: str | None = None, *, database=None) -> bool:
    """Insert a reverse split history entry.

    Args:
        ticker: Symbol associated with the reverse split.
        split_ratio: Reverse split ratio when available.
        split_date: Effective split date string.
        source: Origin identifier for the record.
        ingestion_timestamp: Optional ingestion timestamp override.

    Returns:
        ``True`` when the row is inserted, otherwise ``False`` if SQL logging
        is disabled.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        if ingestion_timestamp:
            cursor.execute(
                """
                INSERT INTO ReverseSplitLog (
                    ticker,
                    split_ratio,
                    split_date,
                    ingestion_timestamp,
                    source
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (ticker.upper(), split_ratio, split_date, ingestion_timestamp, source),
            )
        else:
            cursor.execute(
                """
                INSERT INTO ReverseSplitLog (
                    ticker,
                    split_ratio,
                    split_date,
                    source
                ) VALUES (?, ?, ?, ?)
                """,
                (ticker.upper(), split_ratio, split_date, source),
            )
        conn.commit()
    return True


def fetch_reverse_split_history(ticker: str, *, database=None) -> list[dict[str, str | None]]:
    """Return reverse split history entries for a ticker.

    Args:
        ticker: Symbol to query.

    Returns:
        List of reverse split history rows ordered by newest ingestion
        timestamp first.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ticker, split_ratio, split_date, ingestion_timestamp, source
            FROM ReverseSplitLog
            WHERE ticker = ?
            ORDER BY ingestion_timestamp DESC
            """,
            (ticker.upper(),),
        )
        rows = cursor.fetchall()

    return [
        {
            "ticker": row[0],
            "split_ratio": row[1],
            "split_date": row[2],
            "ingestion_timestamp": row[3],
            "source": row[4],
        }
        for row in rows
    ]


def insert_reverse_split_account_entry(
    account_id: int,
    ticker: str,
    entry_type: str,
    price: float,
    source: str,
    timestamp: str | None = None, *, database=None) -> bool:
    """Insert an append-only account-level reverse split entry.

    Args:
        account_id: Internal account identifier.
        ticker: Symbol associated with the entry.
        entry_type: Entry classification (for example ``cost`` or ``proceeds``).
        price: Price value to persist.
        source: Origin identifier for traceability.
        timestamp: Optional timestamp override.

    Returns:
        ``True`` when inserted, otherwise ``False`` when SQL logging is
        disabled.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        if timestamp:
            cursor.execute(
                """
                INSERT INTO ReverseSplitAccountEntries (
                    account_id,
                    ticker,
                    entry_type,
                    price,
                    timestamp,
                    source
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (account_id, ticker.upper(), entry_type, price, timestamp, source),
            )
        else:
            cursor.execute(
                """
                INSERT INTO ReverseSplitAccountEntries (
                    account_id,
                    ticker,
                    entry_type,
                    price,
                    source
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, ticker.upper(), entry_type, price, source),
            )
        conn.commit()
    return True


def fetch_reverse_split_account_entries(
    account_id: int, ticker: str, *, database=None) -> list[dict[str, Any]]:
    """Return account-level reverse split entries for an account+ticker pair."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT account_id, ticker, entry_type, price, timestamp, source
            FROM ReverseSplitAccountEntries
            WHERE account_id = ? AND ticker = ?
            ORDER BY timestamp DESC, entry_id DESC
            """,
            (account_id, ticker.upper()),
        )
        rows = cursor.fetchall()

    return [
        {
            "account_id": row[0],
            "ticker": row[1],
            "entry_type": row[2],
            "price": row[3],
            "timestamp": row[4],
            "source": row[5],
        }
        for row in rows
    ]
