"""Durable split-event identity and autobuy order-intent records.

An actionable corporate event is identified by normalized
``(ticker, split_date)``. These rows record *intent* to dispatch orders, never
brokerage acknowledgment: after an unknown send or crash the event is left in
``needs_reconciliation`` for an operator rather than silently retried.
"""

from __future__ import annotations

import datetime
import re
import sqlite3
from typing import Iterable, Literal

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import SQL_DATABASE

DATABASE_PATH = SQL_DATABASE

ClaimResult = Literal["claimed", "already_claimed", "invalid", "requires_review"]

UNRESOLVED_STATES = ("claimed", "planned", "needs_reconciliation")
MAX_STALE_DAYS = 14
MAX_FUTURE_DAYS = 400
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
_MAX_TEXT = 200


def _connect(database=None):
    conn = connect_runtime_db(database or DATABASE_PATH)
    run_migrations(conn)
    return conn


def normalize_event(
    ticker: str | None, split_date: str | None, today: datetime.date | None = None
) -> tuple[str, str] | None:
    """Return ``(TICKER, YYYY-MM-DD)`` or ``None`` when unsafe to act on."""
    symbol = (ticker or "").strip().upper()
    if not _TICKER_RE.match(symbol):
        return None
    try:
        parsed = datetime.datetime.strptime((split_date or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    today = today or datetime.date.today()
    if parsed < today - datetime.timedelta(days=MAX_STALE_DAYS):
        return None
    if parsed > today + datetime.timedelta(days=MAX_FUTURE_DAYS):
        return None
    return symbol, parsed.isoformat()


def _bounded(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value)[:_MAX_TEXT]


def claim_split_event(
    ticker: str | None,
    split_date: str | None,
    source_ref: str | None = None,
    *,
    database=None,
) -> ClaimResult:
    """Atomically claim an event so only one caller may schedule its orders.

    ``already_claimed`` also covers a pre-existing watch for the same
    ticker/date that predates intent tracking (recorded as ``submitted``).
    ``requires_review`` means a different-date watch is still active; the
    alert is recorded as ``suppressed`` and nothing may be scheduled.
    """
    event = normalize_event(ticker, split_date)
    if event is None:
        return "invalid"
    symbol, date_iso = event
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            "SELECT 1 FROM split_event_intents WHERE ticker=? AND split_date=?",
            (symbol, date_iso),
        ).fetchone():
            conn.rollback()
            return "already_claimed"
        watch = conn.execute(
            "SELECT split_date FROM split_monitor WHERE ticker=?", (symbol,)
        ).fetchone()
        if watch is not None and watch[0] == date_iso:
            state, reason, result = "submitted", "preexisting_watch", "already_claimed"
        elif watch is not None:
            state, reason, result = (
                "suppressed",
                f"active_watch_for_{watch[0]}"[:_MAX_TEXT],
                "requires_review",
            )
        else:
            state, reason, result = "claimed", None, "claimed"
        conn.execute(
            """INSERT INTO split_event_intents
               (ticker, split_date, source_ref, state, last_reason)
               VALUES (?, ?, ?, ?, ?)""",
            (symbol, date_iso, _bounded(source_ref), state, reason),
        )
        conn.commit()
        return result  # type: ignore[return-value]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _set_event_state(conn, symbol, date_iso, state, reason=None) -> None:
    conn.execute(
        """UPDATE split_event_intents
           SET state=?, last_reason=COALESCE(?, last_reason),
               updated_at=CURRENT_TIMESTAMP
           WHERE ticker=? AND split_date=?""",
        (state, _bounded(reason), symbol, date_iso),
    )


def record_split_order_plan(
    ticker: str,
    split_date: str,
    dispatch_keys: Iterable[str],
    *,
    database=None,
) -> bool:
    """Persist one ``planned`` order intent per stable dispatch key.

    Returns ``False`` (writing nothing) when the event is not in ``claimed``
    state, so a second caller can never re-plan an event.
    """
    symbol, date_iso = ticker.upper(), split_date
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT state FROM split_event_intents WHERE ticker=? AND split_date=?",
            (symbol, date_iso),
        ).fetchone()
        if row is None or row[0] != "claimed":
            conn.rollback()
            return False
        conn.executemany(
            """INSERT OR IGNORE INTO split_event_order_intents
               (ticker, split_date, dispatch_key, state) VALUES (?, ?, ?, 'planned')""",
            [(symbol, date_iso, key) for key in dict.fromkeys(dispatch_keys)],
        )
        _set_event_state(conn, symbol, date_iso, "planned")
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_split_order_queued(
    ticker: str, split_date: str, dispatch_key: str, order_id: str, *, database=None
) -> bool:
    """Record the scheduler order id for a planned dispatch (only once)."""
    conn = _connect(database)
    try:
        cursor = conn.execute(
            """UPDATE split_event_order_intents SET state='queued', order_id=?
               WHERE ticker=? AND split_date=? AND dispatch_key=?
                 AND state='planned'""",
            (order_id, ticker.upper(), split_date, dispatch_key),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def mark_split_event_submitted(ticker: str, split_date: str, *, database=None) -> None:
    """Mark the event handed to the scheduler (not a fill confirmation)."""
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_event_state(conn, ticker.upper(), split_date, "submitted")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_split_event_needs_reconciliation(
    ticker: str, split_date: str, reason: str, *, database=None
) -> None:
    """Flag the event for operator review; never auto-retried."""
    conn = _connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _set_event_state(
            conn, ticker.upper(), split_date, "needs_reconciliation", reason
        )
        conn.execute(
            """UPDATE split_event_order_intents
               SET state='needs_reconciliation', last_error=?
               WHERE ticker=? AND split_date=? AND state='planned'""",
            (_bounded(reason), ticker.upper(), split_date),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def resolve_split_event(
    ticker: str, split_date: str, *, database=None
) -> bool:
    """Operator acknowledgment: close an unresolved event without re-dispatch."""
    conn = _connect(database)
    try:
        cursor = conn.execute(
            """UPDATE split_event_intents
               SET state='suppressed', last_reason='operator_reconciled',
                   updated_at=CURRENT_TIMESTAMP
               WHERE ticker=? AND split_date=? AND state IN (?, ?, ?)""",
            (ticker.upper(), split_date, *UNRESOLVED_STATES),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_unresolved_events(*, database=None) -> list[dict]:
    """Return events needing operator attention (no account identifiers)."""
    conn = _connect(database)
    try:
        rows = conn.execute(
            """SELECT ticker, split_date, state, last_reason, updated_at
               FROM split_event_intents WHERE state IN (?, ?, ?)
               ORDER BY first_seen_at""",
            UNRESOLVED_STATES,
        ).fetchall()
    finally:
        conn.close()
    return [
        {"ticker": t, "split_date": d, "state": s, "reason": r, "updated_at": u}
        for t, d, s, r, u in rows
    ]


def get_split_event(ticker: str, split_date: str, *, database=None) -> dict | None:
    conn = _connect(database)
    try:
        row = conn.execute(
            """SELECT state, last_reason FROM split_event_intents
               WHERE ticker=? AND split_date=?""",
            (ticker.upper(), split_date),
        ).fetchone()
        orders = conn.execute(
            """SELECT dispatch_key, order_id, state FROM split_event_order_intents
               WHERE ticker=? AND split_date=? ORDER BY dispatch_key""",
            (ticker.upper(), split_date),
        ).fetchall()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "state": row[0],
        "reason": row[1],
        "orders": [
            {"dispatch_key": k, "order_id": o, "state": s} for k, o, s in orders
        ],
    }
