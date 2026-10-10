"""Durable account/portfolio value history, separate from investment return.

RSAssistant does not model external deposits/withdrawals, so nothing here is
a time-weighted or money-weighted investment return. These snapshots only
capture observed account/portfolio *value* on each committed holdings
refresh:

- ``positions_value``: sum of security position values for the account.
- ``reported_account_total``: the account total reported by the holdings
  source for that refresh, when exactly one unambiguous value is present.
- ``effective_value``: ``reported_account_total`` when present, otherwise
  ``positions_value``.
"""

from __future__ import annotations

import logging
import math
import sqlite3
from os import PathLike
from typing import Any, Iterable

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import SQL_DATABASE

DATABASE_PATH = SQL_DATABASE
logger = logging.getLogger(__name__)

_BACKFILL_SOURCE_KEY = "historical_holdings_backfill"


def _connect(database: str | PathLike[str] | None = None):
    conn = connect_runtime_db(database or DATABASE_PATH)
    run_migrations(conn)
    return conn


def _finite_or_none(value: Any, field: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _aggregate_current_holdings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Roll ``holdings_current`` up to one row per account for this commit."""

    rows = conn.execute(
        """SELECT account_id,
                  SUM(position_value) AS positions_value,
                  MAX(observed_at) AS observed_at,
                  COUNT(DISTINCT account_total) AS distinct_totals,
                  MAX(account_total) AS any_total
           FROM holdings_current
           GROUP BY account_id"""
    ).fetchall()

    accounts = []
    for account_id, positions_value, observed_at, distinct_totals, any_total in rows:
        reported_total = any_total if distinct_totals == 1 else None
        if distinct_totals and distinct_totals > 1:
            logger.warning(
                "Account %s has %d conflicting reported account totals in this "
                "refresh; falling back to positions_sum instead of averaging.",
                account_id,
                distinct_totals,
            )
        accounts.append(
            {
                "account_id": account_id,
                "positions_value": positions_value or 0.0,
                "reported_account_total": reported_total,
                "observed_at": observed_at,
            }
        )
    return accounts


def record_account_value_snapshots(
    conn: sqlite3.Connection,
    refresh_id: str,
    *,
    source: str,
    observed_at: str | None = None,
    accounts: Iterable[dict[str, Any]] | None = None,
) -> int:
    """Insert one snapshot row per account for this refresh, on ``conn``.

    Must be called inside the same transaction that commits the holdings
    refresh so a rollback of that refresh also rolls back its snapshots.
    When ``accounts`` is omitted, aggregates the ``holdings_current`` rows
    already visible on ``conn`` (i.e. the refresh just committed there).
    """

    if not refresh_id:
        raise ValueError("refresh_id must not be empty")
    if accounts is None:
        accounts = _aggregate_current_holdings(conn)

    rows = []
    for account in accounts:
        account_id = int(account["account_id"])
        positions_value = _finite_or_none(account["positions_value"], "positions_value")
        if positions_value is None:
            raise ValueError("positions_value must not be null")
        reported_total = _finite_or_none(
            account.get("reported_account_total"), "reported_account_total"
        )
        row_observed_at = str(observed_at or account.get("observed_at") or "").strip()
        if not row_observed_at:
            raise ValueError("observed_at is required")

        if reported_total is not None:
            effective_value = reported_total
            valuation_basis = "reported_total"
        else:
            effective_value = positions_value
            valuation_basis = account.get("valuation_basis", "positions_sum")

        rows.append(
            (
                refresh_id,
                account_id,
                row_observed_at,
                positions_value,
                reported_total,
                effective_value,
                valuation_basis,
                source,
            )
        )

    if not rows:
        return 0

    conn.executemany(
        """INSERT INTO account_value_snapshots (
               refresh_id, account_id, observed_at, positions_value,
               reported_account_total, effective_value, valuation_basis, source
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(refresh_id, account_id) DO UPDATE SET
               observed_at=excluded.observed_at,
               positions_value=excluded.positions_value,
               reported_account_total=excluded.reported_account_total,
               effective_value=excluded.effective_value,
               valuation_basis=excluded.valuation_basis,
               source=excluded.source""",
        rows,
    )
    return len(rows)


def list_account_value_snapshots(
    account_ids: Iterable[int] | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    *,
    database: str | PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Return snapshot rows, oldest first, optionally filtered."""

    clauses, params = [], []
    account_ids = list(account_ids) if account_ids is not None else None
    if account_ids:
        clauses.append(f"account_id IN ({', '.join('?' for _ in account_ids)})")
        params.extend(int(a) for a in account_ids)
    if start_at:
        clauses.append("observed_at >= ?")
        params.append(start_at)
    if end_at:
        clauses.append("observed_at <= ?")
        params.append(end_at)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect(database) as conn:
        rows = conn.execute(
            f"""SELECT snapshot_id, refresh_id, account_id, observed_at, positions_value,
                       reported_account_total, effective_value, valuation_basis, source
                FROM account_value_snapshots
                {where}
                ORDER BY observed_at ASC, snapshot_id ASC""",
            params,
        ).fetchall()

    columns = (
        "snapshot_id", "refresh_id", "account_id", "observed_at", "positions_value",
        "reported_account_total", "effective_value", "valuation_basis", "source",
    )
    return [dict(zip(columns, row)) for row in rows]


def latest_account_values(
    account_ids: Iterable[int] | None = None,
    *,
    database: str | PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the most recent snapshot per account."""

    account_ids = list(account_ids) if account_ids is not None else None
    clause, params = "", []
    if account_ids:
        clause = f"WHERE account_id IN ({', '.join('?' for _ in account_ids)})"
        params = [int(a) for a in account_ids]

    with _connect(database) as conn:
        rows = conn.execute(
            f"""SELECT s.account_id, s.observed_at, s.positions_value,
                       s.reported_account_total, s.effective_value, s.valuation_basis,
                       s.source
                FROM account_value_snapshots AS s
                JOIN (
                    SELECT account_id, MAX(snapshot_id) AS snapshot_id
                    FROM account_value_snapshots
                    {clause}
                    GROUP BY account_id
                ) AS latest
                ON latest.account_id = s.account_id AND latest.snapshot_id = s.snapshot_id
                ORDER BY s.account_id""",
            params,
        ).fetchall()

    columns = (
        "account_id", "observed_at", "positions_value", "reported_account_total",
        "effective_value", "valuation_basis", "source",
    )
    return [dict(zip(columns, row)) for row in rows]


def account_value_series(
    account_id: int,
    start_at: str | None = None,
    end_at: str | None = None,
    *,
    database: str | PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Return one account's value history, oldest first."""

    return list_account_value_snapshots(
        account_ids=[account_id], start_at=start_at, end_at=end_at, database=database
    )


def portfolio_value_series(
    start_at: str | None = None,
    end_at: str | None = None,
    *,
    database: str | PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    """Return total effective value across accounts, grouped by refresh, oldest first."""

    clauses, params = [], []
    if start_at:
        clauses.append("observed_at >= ?")
        params.append(start_at)
    if end_at:
        clauses.append("observed_at <= ?")
        params.append(end_at)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect(database) as conn:
        rows = conn.execute(
            f"""SELECT refresh_id, MAX(observed_at) AS observed_at,
                       SUM(effective_value) AS total_effective_value,
                       SUM(positions_value) AS total_positions_value
                FROM account_value_snapshots
                {where}
                GROUP BY refresh_id
                ORDER BY observed_at ASC""",
            params,
        ).fetchall()

    columns = ("refresh_id", "observed_at", "total_effective_value", "total_positions_value")
    return [dict(zip(columns, row)) for row in rows]


def backfill_historical_account_values(*, database: str | PathLike[str] | None = None) -> int:
    """Idempotently backfill positions-value history from ``HistoricalHoldings``.

    Reported account totals are not available in ``HistoricalHoldings``, so
    every backfilled row uses ``valuation_basis='historical_positions_sum'``
    and a ``NULL`` ``reported_account_total``. Safe to call repeatedly: a
    completed backfill is recorded in ``legacy_imports`` and skipped.
    """

    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            "SELECT 1 FROM legacy_imports WHERE source_key=?", (_BACKFILL_SOURCE_KEY,)
        ).fetchone():
            return 0

        rows = conn.execute(
            """SELECT account_id, date, SUM(quantity * average_price) AS positions_value
               FROM HistoricalHoldings
               WHERE account_id IS NOT NULL
               GROUP BY account_id, date"""
        ).fetchall()

        inserted = 0
        for account_id, date, positions_value in rows:
            refresh_id = f"historical:{date}:{account_id}"
            inserted += record_account_value_snapshots(
                conn,
                refresh_id,
                source=_BACKFILL_SOURCE_KEY,
                observed_at=f"{date} 00:00:00",
                accounts=[
                    {
                        "account_id": account_id,
                        "positions_value": positions_value or 0.0,
                        "reported_account_total": None,
                        "valuation_basis": "historical_positions_sum",
                    }
                ],
            )

        conn.execute(
            "INSERT INTO legacy_imports(source_key, imported_rows) VALUES (?, ?)",
            (_BACKFILL_SOURCE_KEY, inserted),
        )
    return inserted


__all__ = [
    "account_value_series",
    "backfill_historical_account_values",
    "latest_account_values",
    "list_account_value_snapshots",
    "portfolio_value_series",
    "record_account_value_snapshots",
]
