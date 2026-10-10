"""SQLite audit log helpers for sent ``!rsa`` commands."""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import SQL_DATABASE, VOLUMES_DIR

# Retained as a one-time import source for installations upgrading from JSON.
ORDER_SEND_LOG_FILE: Path = VOLUMES_DIR / "db" / "order_send_log.json"
DATABASE_PATH = SQL_DATABASE
_MAX_ENTRIES = 1000
_logger = logging.getLogger(__name__)


def _connect():
    conn = connect_runtime_db(DATABASE_PATH)
    run_migrations(conn)
    return conn


def _insert_legacy_entry(conn, entry: dict[str, Any], legacy_key: str) -> None:
    try:
        sent_at = str(entry["sent_at"])
        command = str(entry["command"])
        channel_id = str(entry.get("channel_id", "unknown"))
        ticker = str(entry["ticker"]).upper()
        action = str(entry["action"]).lower()
        quantity = float(entry["quantity"])
        broker = str(entry["broker"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid sent-order entry: {exc}") from exc
    if not all((sent_at.strip(), command.strip(), ticker.strip(), action.strip(), broker.strip())):
        raise ValueError("sent-order entry has an empty required field")
    if not math.isfinite(quantity):
        raise ValueError("sent-order entry has invalid quantity")

    conn.execute(
        """INSERT OR IGNORE INTO rsa_order_send_log (
               sent_at, command, channel_id, ticker, action, quantity, broker,
               legacy_key
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (sent_at, command, channel_id, ticker, action, quantity, broker, legacy_key),
    )


def _import_legacy_send_log(conn) -> None:
    if not ORDER_SEND_LOG_FILE.exists():
        return
    try:
        with ORDER_SEND_LOG_FILE.open("r", encoding="utf-8") as file:
            entries = json.load(file)
    except (OSError, ValueError) as exc:
        _logger.exception("Unable to import legacy sent-order log %s.", ORDER_SEND_LOG_FILE)
        raise RuntimeError(
            f"Unable to import legacy sent-order log: {ORDER_SEND_LOG_FILE}"
        ) from exc
    if not isinstance(entries, list):
        raise ValueError(
            f"Legacy sent-order log must contain a JSON array: {ORDER_SEND_LOG_FILE}"
        )

    conn.execute("BEGIN IMMEDIATE")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            _logger.warning("Skipping malformed legacy sent-order entry %s.", index)
            continue
        try:
            _insert_legacy_entry(
                conn, entry, f"{ORDER_SEND_LOG_FILE.name}:{index}"
            )
        except ValueError as exc:
            _logger.warning("Skipping malformed legacy sent-order entry %s: %s", index, exc)
    conn.commit()
    try:
        ORDER_SEND_LOG_FILE.rename(
            ORDER_SEND_LOG_FILE.with_suffix(ORDER_SEND_LOG_FILE.suffix + ".migrated")
        )
    except OSError:
        # Legacy keys make another import attempt safe if archival fails.
        _logger.exception("Imported sent-order log but could not archive %s.", ORDER_SEND_LOG_FILE)


def _entry_from_row(row) -> dict[str, Any]:
    return {
        "sent_at": row[0],
        "command": row[1],
        "channel_id": row[2],
        "ticker": row[3],
        "action": row[4],
        "quantity": row[5],
        "broker": row[6],
    }


def record_sent_rsa_order(
    *,
    command: str,
    channel_id: int | str | None,
    ticker: str,
    action: str,
    quantity: float,
    broker: str,
    sent_at: datetime | None = None,
) -> dict[str, Any]:
    """Append an audit record for an outbound ``!rsa`` command."""

    timestamp = sent_at or datetime.now(timezone.utc)
    entry = {
        "sent_at": timestamp.astimezone(timezone.utc).isoformat(),
        "command": command,
        "channel_id": str(channel_id) if channel_id is not None else "unknown",
        "ticker": ticker.upper(),
        "action": action.lower(),
        "quantity": quantity,
        "broker": broker,
    }

    with _connect() as conn:
        _import_legacy_send_log(conn)
        conn.execute(
            """INSERT INTO rsa_order_send_log (
                   sent_at, command, channel_id, ticker, action, quantity, broker
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["sent_at"],
                entry["command"],
                entry["channel_id"],
                entry["ticker"],
                entry["action"],
                entry["quantity"],
                entry["broker"],
            ),
        )
        conn.execute(
            """DELETE FROM rsa_order_send_log
               WHERE send_id NOT IN (
                   SELECT send_id FROM rsa_order_send_log
                   ORDER BY send_id DESC LIMIT ?
               )""",
            (_MAX_ENTRIES,),
        )
    return entry


def list_sent_rsa_orders(
    *, limit: int = 10, ticker: str | None = None, action: str | None = None
) -> list[dict[str, Any]]:
    """Return most-recent sent ``!rsa`` audit entries."""

    if limit <= 0:
        return []

    clauses = []
    parameters: list[Any] = []
    if ticker:
        clauses.append("ticker = ?")
        parameters.append(ticker.upper())
    if action:
        clauses.append("action = ?")
        parameters.append(action.lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with _connect() as conn:
        _import_legacy_send_log(conn)
        rows = conn.execute(
            f"""SELECT sent_at, command, channel_id, ticker, action, quantity, broker
                FROM rsa_order_send_log {where}
                ORDER BY send_id DESC LIMIT ?""",
            (*parameters, limit),
        ).fetchall()
    return [_entry_from_row(row) for row in rows]


def latest_sent_rsa_order(ticker: str | None = None) -> dict[str, Any] | None:
    """Return the latest sent ``!rsa`` entry, optionally constrained by ticker."""

    entries = list_sent_rsa_orders(limit=1, ticker=ticker)
    return entries[0] if entries else None
