"""Transactional SQLite persistence for scheduled orders."""

import json
import logging
from datetime import datetime
from pathlib import Path

from utils.config_utils import SQL_DATABASE, VOLUMES_DIR
from utils.db import connect_database, run_migrations

# Retained as a one-time import source for installations upgrading from JSON.
QUEUE_FILE = VOLUMES_DIR / "db" / "order_queue.json"
DATABASE_PATH = SQL_DATABASE
logger = logging.getLogger(__name__)


def _connect():
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = connect_database(DATABASE_PATH)
    run_migrations(conn)
    return conn


def _import_legacy_queue(conn) -> None:
    """Import old JSON queue entries idempotently, preserving the source file."""
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
    conn.executemany(
        "INSERT OR IGNORE INTO order_queue(order_id, order_data) VALUES (?, ?)",
        [(str(order_id), json.dumps(data)) for order_id, data in legacy.items()],
    )
    conn.commit()
    try:
        QUEUE_FILE.rename(QUEUE_FILE.with_suffix(QUEUE_FILE.suffix + ".migrated"))
    except OSError:
        # Import is committed and idempotent; retain the source for recovery.
        logger.exception("Imported queue but could not archive %s.", QUEUE_FILE)


def _load_queue(conn=None):
    if conn is None:
        with _connect() as db:
            _import_legacy_queue(db)
            rows = db.execute("SELECT order_id, order_data FROM order_queue").fetchall()
    else:
        _import_legacy_queue(conn)
        rows = conn.execute("SELECT order_id, order_data FROM order_queue").fetchall()
    return {order_id: json.loads(data) for order_id, data in rows}


def add_to_order_queue(order_id, order_data):
    """Atomically add or replace a scheduled order."""
    with _connect() as conn:
        _import_legacy_queue(conn)
        conn.execute(
            """INSERT INTO order_queue(order_id, order_data) VALUES (?, ?)
               ON CONFLICT(order_id) DO UPDATE SET order_data=excluded.order_data,
                   updated_at=DATETIME('now')""",
            (str(order_id), json.dumps(order_data)),
        )


def get_order_queue():
    """Return queued orders keyed by ID."""
    return _load_queue()


def remove_order(order_id):
    """Atomically remove an order; return whether one existed."""
    with _connect() as conn:
        _import_legacy_queue(conn)
        cursor = conn.execute("DELETE FROM order_queue WHERE order_id=?", (str(order_id),))
        return cursor.rowcount > 0


def update_order_time(order_id, new_time: str) -> bool:
    with _connect() as conn:
        _import_legacy_queue(conn)
        row = conn.execute(
            "SELECT order_data FROM order_queue WHERE order_id=?", (str(order_id),)
        ).fetchone()
        if row is None:
            return False
        data = json.loads(row[0])
        data["time"] = new_time
        conn.execute(
            "UPDATE order_queue SET order_data=?, updated_at=DATETIME('now') WHERE order_id=?",
            (json.dumps(data), str(order_id)),
        )
        return True


def clear_order_queue():
    with _connect() as conn:
        _import_legacy_queue(conn)
        conn.execute("DELETE FROM order_queue")


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
