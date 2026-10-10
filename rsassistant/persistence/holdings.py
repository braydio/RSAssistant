"""Atomic current holdings snapshots and refresh staging."""

from __future__ import annotations

import logging
import math
import sqlite3
from datetime import datetime, timedelta
from os import PathLike
from typing import Any, Iterable

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from rsassistant.persistence import accounts
from utils.config_utils import SQL_DATABASE, get_account_nickname_or_default

DATABASE_PATH = SQL_DATABASE
logger = logging.getLogger(__name__)


def _get_db_connection(database=None):
    return connect_runtime_db(database or DATABASE_PATH)

_SNAPSHOT_FIELDS = (
    "account_id",
    "ticker",
    "quantity",
    "price",
    "position_value",
    "account_total",
    "observed_at",
    "source",
)


def _finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid holdings {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"Holdings {field} must be finite")
    return number


def _prepare_holdings(
    holdings: Iterable[dict[str, Any]], source: str
) -> list[dict[str, Any]]:
    positions: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for index, item in enumerate(holdings, start=1):
        try:
            broker_raw = item["broker"]
            broker_number_raw = item.get("broker_number", "")
            account_number_raw = item["account_number"]
            ticker_raw = item["ticker"]
            broker = str(broker_raw or "").strip()
            broker_number = str(broker_number_raw or "").strip()
            account_number = str(account_number_raw or "").strip()
            ticker = str(ticker_raw or "").strip().upper()
            quantity = _finite_number(item["quantity"], "quantity")
            price = _finite_number(item["price"], "price")
            position_value = _finite_number(
                item.get("position_value", quantity * price), "position_value"
            )
            account_total_raw = item.get("account_total")
            account_total = (
                None
                if account_total_raw in (None, "")
                else _finite_number(account_total_raw, "account_total")
            )
            observed_at = str(item["observed_at"]).strip()
            row_source = str(item.get("source") or source).strip()
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Invalid holdings row {index}: missing required data") from exc

        if not broker or not account_number or not ticker:
            raise ValueError(f"Invalid holdings row {index}: empty account or ticker")
        if not row_source:
            raise ValueError(f"Invalid holdings row {index}: empty source")
        try:
            datetime.fromisoformat(observed_at)
        except ValueError as exc:
            raise ValueError(
                f"Invalid holdings observed_at in row {index}: {observed_at!r}"
            ) from exc

        key = (broker, broker_number, account_number, ticker)
        positions[key] = {
            "broker": broker,
            "broker_number": broker_number,
            "account_number": account_number,
            "ticker": ticker,
            "quantity": quantity,
            "price": price,
            "position_value": position_value,
            "account_total": account_total,
            "observed_at": observed_at,
            "source": row_source,
        }
    return list(positions.values())


def _connect(database: str | PathLike[str] | None = None):
    conn = connect_runtime_db(database or DATABASE_PATH)
    run_migrations(conn)
    return conn


def _resolve_account_ids(conn, positions: list[dict[str, Any]]) -> None:
    for position in positions:
        conn.execute(
            """INSERT INTO Accounts(broker, broker_number, account_number)
               VALUES (?, ?, ?)
               ON CONFLICT(broker, broker_number, account_number) DO NOTHING""",
            (
                position["broker"],
                position["broker_number"],
                position["account_number"],
            ),
        )
        row = conn.execute(
            """SELECT account_id FROM Accounts
               WHERE broker=? AND broker_number=? AND account_number=?""",
            (
                position["broker"],
                position["broker_number"],
                position["account_number"],
            ),
        ).fetchone()
        position["account_id"] = int(row[0])


def _insert_positions(conn, table: str, positions: list[dict[str, Any]], refresh_id=None):
    prefix = (refresh_id,) if refresh_id is not None else ()
    columns = ("refresh_id", *_SNAPSHOT_FIELDS) if refresh_id is not None else _SNAPSHOT_FIELDS
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        [
            (
                *prefix,
                position["account_id"],
                position["ticker"],
                position["quantity"],
                position["price"],
                position["position_value"],
                position["account_total"],
                position["observed_at"],
                position["source"],
            )
            for position in positions
        ],
    )


def replace_current_holdings(
    holdings: Iterable[dict[str, Any]],
    *,
    source: str = "holdings_snapshot",
    database: str | PathLike[str] | None = None,
) -> int:
    """Atomically replace all current positions with a validated snapshot."""

    positions = _prepare_holdings(holdings, source)
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _resolve_account_ids(conn, positions)
        conn.execute("DELETE FROM holdings_current")
        _insert_positions(conn, "holdings_current", positions)
    return len(positions)


def stage_current_holdings(
    refresh_id: str,
    holdings: Iterable[dict[str, Any]],
    *,
    source: str = "holdings_refresh",
    database: str | PathLike[str] | None = None,
) -> int:
    """Replace one staged refresh generation without exposing it as current."""

    if not refresh_id:
        raise ValueError("refresh_id must not be empty")
    positions = _prepare_holdings(holdings, source)
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _resolve_account_ids(conn, positions)
        conn.execute(
            "INSERT INTO holdings_refreshes(refresh_id) VALUES (?) "
            "ON CONFLICT(refresh_id) DO NOTHING",
            (str(refresh_id),),
        )
        conn.execute(
            "DELETE FROM holdings_refresh_staging WHERE refresh_id=?",
            (str(refresh_id),),
        )
        _insert_positions(
            conn, "holdings_refresh_staging", positions, str(refresh_id)
        )
    return len(positions)


def activate_staged_holdings(
    refresh_id: str, *, database: str | PathLike[str] | None = None
) -> bool:
    """Atomically publish a staged refresh; return false when it is missing."""

    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute(
            "SELECT 1 FROM holdings_refreshes WHERE refresh_id=?",
            (str(refresh_id),),
        ).fetchone():
            return False
        conn.execute("DELETE FROM holdings_current")
        conn.execute(
            f"""INSERT INTO holdings_current ({', '.join(_SNAPSHOT_FIELDS)})
                SELECT {', '.join(_SNAPSHOT_FIELDS)} FROM holdings_refresh_staging
                WHERE refresh_id=?""",
            (str(refresh_id),),
        )
        conn.execute(
            "DELETE FROM holdings_refreshes WHERE refresh_id=?", (str(refresh_id),)
        )
    return True


def discard_staged_holdings(
    refresh_id: str, *, database: str | PathLike[str] | None = None
) -> None:
    """Discard a refresh that was aborted before activation."""

    with _connect(database) as conn:
        conn.execute("DELETE FROM holdings_refreshes WHERE refresh_id=?", (str(refresh_id),))


def get_current_holdings(
    *, database: str | PathLike[str] | None = None
) -> list[dict[str, Any]]:
    """Return current positions with their account identity."""

    with _connect(database) as conn:
        rows = conn.execute(
            """SELECT h.account_id, a.broker, a.broker_number, a.account_number,
                      h.ticker, h.quantity, h.price, h.position_value,
                      h.account_total, h.observed_at, h.source
               FROM holdings_current AS h
               JOIN Accounts AS a ON a.account_id=h.account_id
               ORDER BY a.broker, a.broker_number, a.account_number, h.ticker"""
        ).fetchall()
    columns = (
        "account_id",
        "broker",
        "broker_number",
        "account_number",
        "ticker",
        "quantity",
        "price",
        "position_value",
        "account_total",
        "observed_at",
        "source",
    )
    return [dict(zip(columns, row)) for row in rows]


def clear_current_holdings(*, database: str | PathLike[str] | None = None) -> None:
    """Clear the authoritative current snapshot."""
    with _connect(database) as conn:
        conn.execute("DELETE FROM holdings_current")


def latest_holdings_timestamp(*, database: str | PathLike[str] | None = None):
    """Return the newest observation timestamp, or ``None`` for an empty snapshot."""
    with _connect(database) as conn:
        row = conn.execute("SELECT MAX(observed_at) FROM holdings_current").fetchone()
    return row[0] if row and row[0] else None


__all__ = [
    "activate_staged_holdings",
    "discard_staged_holdings",
    "get_current_holdings",
    "clear_current_holdings",
    "latest_holdings_timestamp",
    "replace_current_holdings",
    "stage_current_holdings",
]


def update_holdings_live(
    broker, broker_number, account_number, ticker, quantity, price, *, database=None):
    """Insert a holding into ``HoldingsLive`` when logging is enabled."""


    logger.info(
        f"Updating holdings for ticker {ticker}, broker {broker}, account {account_number}."
    )
    account_id = accounts.get_or_create_account_id(broker, broker_number, account_number, database=database)

    with _get_db_connection(database) as conn:
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


def update_holdings_live_batch(holdings: list[dict[str, Any]], *, database=None) -> int:
    """Insert many holdings into ``HoldingsLive`` in a single DB transaction.

    Args:
        holdings: Items with keys ``broker``, ``broker_number``,
            ``account_number``, ``ticker``, ``quantity``, and ``price``.

    Returns:
        Number of rows inserted into ``HoldingsLive``.
    """


    if not holdings:
        return 0

    inserted_rows = 0
    account_id_cache: dict[tuple[str, str, str], int] = {}

    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        rows_to_insert: list[tuple[int, str, float, float]] = []

        for item in holdings:
            broker = str(item.get("broker", "")).strip()
            broker_number = str(item.get("broker_number", "")).strip()
            account_number = str(item.get("account_number", "")).strip()
            ticker = str(item.get("ticker", "")).strip()
            if not (broker and account_number and ticker):
                continue

            try:
                quantity = float(item.get("quantity", 0))
                price = float(item.get("price", 0))
            except (TypeError, ValueError):
                continue
            if quantity < 0:
                continue

            account_key = (broker, broker_number, account_number)
            account_id = account_id_cache.get(account_key)
            if account_id is None:
                account_nickname = get_account_nickname_or_default(
                    broker, broker_number, account_number
                )
                cursor.execute(
                    """
                    INSERT INTO Accounts (
                        broker, account_number, broker_number, account_nickname
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(broker, broker_number, account_number) DO NOTHING
                    """,
                    (broker, account_number, broker_number, account_nickname),
                )
                cursor.execute(
                    """SELECT account_id FROM Accounts
                       WHERE broker=? AND broker_number=? AND account_number=?""",
                    (broker, broker_number, account_number),
                )
                account_id = int(cursor.fetchone()[0])
                account_id_cache[account_key] = account_id

            rows_to_insert.append((account_id, ticker, quantity, price))

        if rows_to_insert:
            cursor.executemany(
                """
                INSERT INTO HoldingsLive (account_id, ticker, quantity, average_price, timestamp)
                VALUES (?, ?, ?, ?, DATETIME('now'))
                """,
                rows_to_insert,
            )
            inserted_rows = len(rows_to_insert)
            logger.info("Holdings batch update inserted %d rows.", inserted_rows)

    return inserted_rows


def update_historical_holdings(target_date: str | None = None, *, database=None) -> int:
    """Upsert the latest observation per holding for one business date."""
    logger.info("Updating historical holdings based on live data.")
    target_date = target_date or (datetime.now() - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )

    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO HistoricalHoldings (
                    account_id, ticker, date, quantity, average_price
                )
                SELECT live.account_id, live.ticker, DATE(live.timestamp),
                       live.quantity, live.average_price
                FROM HoldingsLive AS live
                WHERE DATE(live.timestamp) = ?
                  AND live.holding_id = (
                      SELECT MAX(latest.holding_id)
                      FROM HoldingsLive AS latest
                      WHERE latest.account_id IS live.account_id
                        AND latest.ticker = live.ticker
                        AND DATE(latest.timestamp) = DATE(live.timestamp)
                  )
                ON CONFLICT(account_id, ticker, date) DO UPDATE SET
                    quantity = excluded.quantity,
                    average_price = excluded.average_price
                """,
                (target_date,),
            )
            conn.commit()
            logger.info("Historical holdings updated successfully.")
            return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"Error updating historical holdings: {e}")
            raise
