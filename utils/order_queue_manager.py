"""Transactional SQLite persistence for scheduled orders."""

import json
import logging
import math
from datetime import datetime

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import SQL_DATABASE, VOLUMES_DIR

# Retained as a one-time import source for installations upgrading from JSON.
QUEUE_FILE = VOLUMES_DIR / "db" / "order_queue.json"
DATABASE_PATH = SQL_DATABASE
logger = logging.getLogger(__name__)

_QUEUE_FIELDS = {"action", "ticker", "quantity", "broker", "time"}


def _connect():
    conn = connect_runtime_db(DATABASE_PATH)
    run_migrations(conn)
    return conn


def _record_values(order_id, data, created_at=None, updated_at=None):
    if not isinstance(data, dict):
        raise ValueError("queue entry must be a JSON object")

    missing = _QUEUE_FIELDS - data.keys()
    if missing:
        raise ValueError(f"queue entry is missing required fields: {sorted(missing)}")

    try:
        quantity = float(data["quantity"])
        attempt_count = int(data.get("attempt_count", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("queue entry has invalid numeric fields") from exc

    extras = {key: value for key, value in data.items() if key not in _QUEUE_FIELDS}
    if not all(
        str(data[key]).strip() for key in ("action", "ticker", "broker", "time")
    ):
        raise ValueError("queue entry has an empty required field")
    if not math.isfinite(quantity) or attempt_count < 0:
        raise ValueError("queue entry has invalid numeric fields")
    state = str(data.get("status", "pending")).lower()
    return (
        str(order_id),
        str(data["action"]),
        str(data["ticker"]),
        quantity,
        str(data["broker"]),
        str(data["time"]),
        state,
        attempt_count,
        data.get("last_error"),
        json.dumps(extras),
        created_at,
        updated_at,
    )


def _insert_queue_record(conn, order_id, data, *, ignore=False):
    values = _record_values(order_id, data)
    verb = "INSERT OR IGNORE" if ignore else "INSERT"
    conn.execute(
        f"""{verb} INTO scheduled_orders (
               order_id, action, ticker, quantity, broker, scheduled_at,
               state, attempt_count, last_error, metadata_json,
               created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
               COALESCE(?, CURRENT_TIMESTAMP), COALESCE(?, CURRENT_TIMESTAMP))""",
        values,
    )


def _import_legacy_queue(conn) -> None:
    """Import the legacy JSON queue transactionally and idempotently."""
    if not QUEUE_FILE.exists():
        return
    try:
        with QUEUE_FILE.open(encoding="utf-8") as stream:
            legacy = json.load(stream)
    except (OSError, ValueError) as exc:
        logger.exception("Unable to import legacy order queue %s.", QUEUE_FILE)
        raise RuntimeError(f"Unable to import legacy order queue: {QUEUE_FILE}") from exc
    if not isinstance(legacy, dict):
        raise ValueError(f"Legacy order queue must contain a JSON object: {QUEUE_FILE}")

    conn.execute("BEGIN IMMEDIATE")
    for order_id, data in legacy.items():
        try:
            _insert_queue_record(conn, order_id, data, ignore=True)
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping malformed legacy order %s: %s", order_id, exc)
    conn.commit()
    try:
        QUEUE_FILE.rename(QUEUE_FILE.with_suffix(QUEUE_FILE.suffix + ".migrated"))
    except OSError:
        # Import is committed and idempotent; retain the source for recovery.
        logger.exception("Imported queue but could not archive %s.", QUEUE_FILE)


def _row_to_data(row):
    order_id, action, ticker, quantity, broker, scheduled_at, metadata_json = row
    data = json.loads(metadata_json)
    data.update(
        {
            "action": action,
            "ticker": ticker,
            "quantity": quantity,
            "broker": broker,
            "time": scheduled_at,
        }
    )
    return str(order_id), data


def _load_queue(conn=None):
    if conn is None:
        with _connect() as db:
            _import_legacy_queue(db)
            rows = db.execute(
                """SELECT order_id, action, ticker, quantity, broker, scheduled_at,
                          metadata_json FROM scheduled_orders"""
            ).fetchall()
    else:
        _import_legacy_queue(conn)
        rows = conn.execute(
            """SELECT order_id, action, ticker, quantity, broker, scheduled_at,
                      metadata_json FROM scheduled_orders"""
        ).fetchall()
    return dict(_row_to_data(row) for row in rows)


def add_to_order_queue(order_id, order_data):
    """Atomically add or replace a scheduled order."""
    with _connect() as conn:
        _import_legacy_queue(conn)
        values = _record_values(order_id, order_data)
        conn.execute(
            """INSERT INTO scheduled_orders (
                   order_id, action, ticker, quantity, broker, scheduled_at,
                   state, attempt_count, last_error, metadata_json,
                   created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   COALESCE(?, CURRENT_TIMESTAMP), COALESCE(?, CURRENT_TIMESTAMP))
               ON CONFLICT(order_id) DO UPDATE SET
                   action=excluded.action,
                   ticker=excluded.ticker,
                   quantity=excluded.quantity,
                   broker=excluded.broker,
                   scheduled_at=excluded.scheduled_at,
                   state=excluded.state,
                   attempt_count=excluded.attempt_count,
                   last_error=excluded.last_error,
                   metadata_json=excluded.metadata_json,
                   updated_at=CURRENT_TIMESTAMP""",
            values,
        )


def get_order_queue():
    """Return queued orders keyed by ID."""
    return _load_queue()


def remove_order(order_id):
    """Atomically remove an order; return whether one existed."""
    with _connect() as conn:
        _import_legacy_queue(conn)
        cursor = conn.execute(
            "DELETE FROM scheduled_orders WHERE order_id=?", (str(order_id),)
        )
        return cursor.rowcount > 0


def update_order_time(order_id, new_time: str) -> bool:
    with _connect() as conn:
        _import_legacy_queue(conn)
        cursor = conn.execute(
            """UPDATE scheduled_orders
               SET scheduled_at=?, updated_at=CURRENT_TIMESTAMP
               WHERE order_id=?""",
            (new_time, str(order_id)),
        )
        return cursor.rowcount > 0


def clear_order_queue():
    with _connect() as conn:
        _import_legacy_queue(conn)
        conn.execute("DELETE FROM scheduled_orders")


def list_order_queue():
    queue = get_order_queue()
    return [
        f"{oid} → {data['action']} {data['quantity']} {data['ticker']} via {data['broker']} at {data['time']}"
        for oid, data in queue.items()
    ]


def list_order_queue_items():
    return list(get_order_queue().items())


def get_past_due_orders(reference_time) -> list[tuple[str, dict]]:
    queue = get_order_queue()
    past_due = []
    for order_id, data in queue.items():
        try:
            execution_time = datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")
        except (KeyError, TypeError, ValueError):
            continue
        if execution_time <= reference_time:
            past_due.append((order_id, data))
    return past_due
