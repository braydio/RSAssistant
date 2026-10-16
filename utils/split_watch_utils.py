"""SQLite persistence for reverse-split monitor state."""

from __future__ import annotations

import datetime
import json
import logging

from rsassistant.persistence import split_events
from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import SQL_DATABASE, VOLUMES_DIR

SPLIT_WATCH_DIR = VOLUMES_DIR / "db"
# Legacy migration input only; runtime writes go to SQLite.
SPLIT_WATCH_FILE = SPLIT_WATCH_DIR / "split_watchlist.json"
DATABASE_PATH = SQL_DATABASE
logger = logging.getLogger(__name__)


def _connect():
    conn = connect_runtime_db(DATABASE_PATH)
    run_migrations(conn)
    return conn


def _account_names(value, ticker: str, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        logger.warning("Skipping invalid %s list for legacy split ticker %s.", field, ticker)
        return []
    return [str(name) for name in value if name is not None and str(name)]


def _import_legacy_watchlist(conn) -> None:
    if not SPLIT_WATCH_FILE.exists():
        return
    try:
        with SPLIT_WATCH_FILE.open("r", encoding="utf-8") as file:
            legacy = json.load(file)
    except (OSError, ValueError) as exc:
        logger.exception("Unable to import legacy split watchlist %s.", SPLIT_WATCH_FILE)
        raise RuntimeError(
            f"Unable to import legacy split watchlist: {SPLIT_WATCH_FILE}"
        ) from exc
    watchlist = legacy.get("watchlist") if isinstance(legacy, dict) else None
    if not isinstance(watchlist, dict):
        raise ValueError(
            f"Legacy split watchlist must contain a watchlist object: {SPLIT_WATCH_FILE}"
        )

    conn.execute("BEGIN IMMEDIATE")
    for raw_ticker, info in watchlist.items():
        ticker = str(raw_ticker).upper()
        if not isinstance(info, dict) or not info.get("split_date"):
            logger.warning("Skipping malformed legacy split ticker %s.", ticker)
            continue
        status = str(info.get("status", "buying")).lower()
        if status not in {"buying", "selling"}:
            logger.warning("Skipping legacy split ticker %s with invalid status.", ticker)
            continue
        split_date = str(info["split_date"])
        conn.execute(
            """INSERT OR IGNORE INTO split_monitor(ticker, split_date, status)
               VALUES (?, ?, ?)""",
            (ticker, split_date, status),
        )
        bought_names = _account_names(info.get("accounts_bought", []), ticker, "bought")
        sold_names = _account_names(info.get("accounts_sold", []), ticker, "sold")
        bought = set(bought_names)
        sold = set(sold_names)
        for account_name in dict.fromkeys([*bought_names, *sold_names]):
            conn.execute(
                """INSERT OR IGNORE INTO split_monitor_accounts
                   (ticker, account_name, bought, sold) VALUES (?, ?, ?, ?)""",
                (ticker, account_name, account_name in bought, account_name in sold),
            )
    conn.commit()
    try:
        SPLIT_WATCH_FILE.rename(
            SPLIT_WATCH_FILE.with_suffix(SPLIT_WATCH_FILE.suffix + ".migrated")
        )
    except OSError:
        logger.exception("Imported split watchlist but could not archive %s.", SPLIT_WATCH_FILE)


def _get_full_watchlist(conn) -> dict[str, dict]:
    rows = conn.execute(
        """SELECT m.ticker, m.split_date, m.status,
                  a.account_name, a.bought, a.sold
           FROM split_monitor AS m
           LEFT JOIN split_monitor_accounts AS a ON a.ticker = m.ticker
           ORDER BY m.rowid, a.rowid"""
    ).fetchall()
    watchlist: dict[str, dict] = {}
    for ticker, split_date, status, account_name, bought, sold in rows:
        info = watchlist.setdefault(
            ticker,
            {
                "split_date": split_date,
                "status": status,
                "accounts_bought": [],
                "accounts_sold": [],
            },
        )
        if account_name is None:
            continue
        if bought:
            info["accounts_bought"].append(account_name)
        if sold:
            info["accounts_sold"].append(account_name)
    return watchlist


def load_data():
    """Compatibility initializer that migrates and returns current SQL state."""
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        return {"watchlist": _get_full_watchlist(conn)}


def add_split_watch(ticker, split_date):
    ticker = ticker.upper()
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        conn.execute(
            """INSERT OR IGNORE INTO split_monitor(ticker, split_date, status)
               VALUES (?, ?, 'buying')""",
            (ticker, split_date),
        )


def mark_account_bought(ticker, account_name):
    ticker = ticker.upper()
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        if conn.execute(
            "SELECT 1 FROM split_monitor WHERE ticker=?", (ticker,)
        ).fetchone():
            conn.execute(
                """INSERT INTO split_monitor_accounts
                   (ticker, account_name, bought, sold) VALUES (?, ?, 1, 0)
                   ON CONFLICT(ticker, account_name) DO UPDATE SET bought=1""",
                (ticker, account_name),
            )


def update_split_status():
    today = datetime.date.today()
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        rows = conn.execute(
            "SELECT ticker, split_date FROM split_monitor WHERE status='buying'"
        ).fetchall()
        transitioned = []
        for ticker, split_date in rows:
            parsed_date = _parse_split_date(split_date)
            if parsed_date is not None and parsed_date <= today:
                transitioned.append(ticker)
        conn.executemany(
            """UPDATE split_monitor SET status='selling', updated_at=CURRENT_TIMESTAMP
               WHERE ticker=?""",
            [(ticker,) for ticker in transitioned],
        )
        return transitioned


def mark_account_sold(ticker, account_name):
    ticker = ticker.upper()
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        if conn.execute(
            "SELECT 1 FROM split_monitor WHERE ticker=?", (ticker,)
        ).fetchone():
            conn.execute(
                """INSERT INTO split_monitor_accounts
                   (ticker, account_name, bought, sold) VALUES (?, ?, 0, 1)
                   ON CONFLICT(ticker, account_name) DO UPDATE SET sold=1""",
                (ticker, account_name),
            )


def is_split_complete(info: dict) -> bool:
    """Conservative completion test: selling, bought, and every bought account sold."""
    bought = set(info.get("accounts_bought", []))
    sold = set(info.get("accounts_sold", []))
    return info.get("status") == "selling" and bool(bought) and bought <= sold


def split_phase(info: dict, unresolved: bool = False, today=None) -> str:
    """Return buying | selling | overdue | reconciliation needed for display."""
    if unresolved:
        return "reconciliation needed"
    today = today or datetime.date.today()
    split_dt = _parse_split_date(info.get("split_date"))
    if split_dt is not None and split_dt < today and not is_split_complete(info):
        return "overdue"
    return info.get("status", "unknown")


def _unresolved_pairs(conn) -> set[tuple[str, str]]:
    return {
        (ticker, split_date)
        for ticker, split_date in conn.execute(
            "SELECT ticker, split_date FROM split_event_intents "
            "WHERE state='needs_reconciliation'"
        )
    }


def _delete_completed(conn) -> list[str]:
    blocked = _unresolved_pairs(conn)
    completed = [
        ticker
        for ticker, info in _get_full_watchlist(conn).items()
        if is_split_complete(info) and (ticker, info["split_date"]) not in blocked
    ]
    if completed:
        conn.executemany(
            "DELETE FROM split_monitor WHERE ticker=?",
            [(ticker,) for ticker in completed],
        )
    return completed


def cleanup_completed_tickers():
    """Archive watches proven complete; return their tickers.

    Event intent history is retained in ``split_event_intents``.
    """
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        return _delete_completed(conn)


def cleanup_expired_tickers():
    """Archive only proven-complete watches.

    Date passage alone never deletes an open watch; overdue entries stay
    visible (see :func:`split_phase`). Name and return type are kept for
    existing callers.
    """
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        return _delete_completed(conn)


def get_watchlist():
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        return [
            row[0]
            for row in conn.execute(
                "SELECT ticker FROM split_monitor ORDER BY rowid"
            ).fetchall()
        ]


def get_status(ticker):
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        return _get_full_watchlist(conn).get(ticker.upper())


def get_full_watchlist():
    """Return the full watchlist dictionary."""
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        return _get_full_watchlist(conn)


def remove_split_watch(ticker: str) -> bool:
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        cursor = conn.execute(
            "DELETE FROM split_monitor WHERE ticker=?", (ticker.upper(),)
        )
        return cursor.rowcount > 0


def get_all_accounts():
    """Return account names marked as holding a watched ticker."""
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        return {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT account_name FROM split_monitor_accounts WHERE bought=1"
            ).fetchall()
        }


def _parse_split_date(split_date: str | None) -> datetime.date | None:
    if not split_date:
        return None
    try:
        return datetime.datetime.strptime(split_date, "%Y-%m-%d").date()
    except ValueError:
        return None


def claim_split_event(ticker, split_date, source_ref=None):
    """Atomically claim ``(ticker, split_date)``; see persistence.split_events."""
    return split_events.claim_split_event(
        ticker, split_date, source_ref, database=DATABASE_PATH
    )


def record_split_order_plan(ticker, split_date, dispatch_keys):
    return split_events.record_split_order_plan(
        ticker, split_date, dispatch_keys, database=DATABASE_PATH
    )


def mark_split_order_queued(ticker, split_date, dispatch_key, order_id):
    return split_events.mark_split_order_queued(
        ticker, split_date, dispatch_key, order_id, database=DATABASE_PATH
    )


def mark_split_event_submitted(ticker, split_date):
    split_events.mark_split_event_submitted(ticker, split_date, database=DATABASE_PATH)


def mark_split_event_needs_reconciliation(ticker, split_date, reason):
    split_events.mark_split_event_needs_reconciliation(
        ticker, split_date, reason, database=DATABASE_PATH
    )


def resolve_split_event(ticker, split_date):
    return split_events.resolve_split_event(ticker, split_date, database=DATABASE_PATH)


def list_unresolved_events():
    return split_events.list_unresolved_events(database=DATABASE_PATH)


def replace_split_watch(ticker, split_date) -> bool:
    """Operator path: replace an active watch with a later split date.

    Old account markers are dropped (not carried over); the old event intent
    record is preserved. The new event is recorded ``suppressed`` so alert
    replays cannot auto-schedule buys for it.
    """
    event = split_events.normalize_event(ticker, split_date)
    if event is None:
        return False
    symbol, date_iso = event
    with _connect() as conn:
        _import_legacy_watchlist(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM split_monitor WHERE ticker=?", (symbol,))
        conn.execute(
            "INSERT INTO split_monitor(ticker, split_date, status) VALUES (?, ?, 'buying')",
            (symbol, date_iso),
        )
        conn.execute(
            """INSERT OR IGNORE INTO split_event_intents
               (ticker, split_date, state, last_reason)
               VALUES (?, ?, 'suppressed', 'operator_replaced')""",
            (symbol, date_iso),
        )
    return True
