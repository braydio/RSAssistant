"""Order intent / broker receipt repository.

Invariants: a Discord send is only ever ``dispatched``; a bot confirmation text
is only ``accepted_reported`` evidence (grade ``legacy_text``); nothing here
creates an ``execution_fills`` row or marks an intent ``filled``. Unlinked or
ambiguous evidence is kept and flagged ``needs_review`` -- never guessed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from os import PathLike
from typing import Any

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import SQL_DATABASE

# Receipts only link to an intent dispatched within this window.
LINK_WINDOW = timedelta(hours=6)
_OPEN_STATES = ("dispatched", "broker_accepted", "partially_filled")


def _connect(database: str | PathLike[str] | None = None):
    conn = connect_runtime_db(database or SQL_DATABASE)
    run_migrations(conn)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_intent_for_send(
    send_id: int,
    *,
    ticker: str,
    action: str,
    quantity: float,
    broker: str,
    command: str | None = None,
    channel_id: str | None = None,
    created_at: str | None = None,
    source: str = "live",
    database: str | PathLike[str] | None = None,
) -> str:
    """Create (idempotently, keyed by ``send_id``) the intent for one send."""

    backfill = source == "send_log_backfill"
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT intent_id FROM order_intents WHERE send_id=?", (send_id,)
        ).fetchone()
        if row:
            return row[0]
        intent_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO order_intents
               (intent_id, send_id, source, created_at, ticker, action, quantity,
                broker, command, channel_id, state, evidence_grade, needs_review)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                intent_id, send_id, source, created_at or _now(), ticker.upper(),
                action.lower(), quantity, broker, command, channel_id,
                "unknown" if backfill else "dispatched",
                "discord_send_only", 1 if backfill else 0,
            ),
        )
    return intent_id


def record_receipt(
    *,
    outcome: str,
    evidence: str,
    discord_message_id: str | int | None = None,
    broker: str | None = None,
    broker_group: str | None = None,
    account_last4: str | None = None,
    ticker: str | None = None,
    action: str | None = None,
    quantity: float | None = None,
    received_at: datetime | None = None,
    database: str | PathLike[str] | None = None,
) -> int | None:
    """Store one bot message as evidence and link it only when unambiguous.

    Returns the receipt id, or ``None`` if this Discord message was already
    recorded (replays are no-ops).
    """

    when = (received_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if discord_message_id is not None and conn.execute(
            "SELECT 1 FROM broker_order_receipts WHERE discord_message_id=?",
            (str(discord_message_id),),
        ).fetchone():
            return None
        intent_id = None
        if ticker and action:
            cutoff = (when - LINK_WINDOW).isoformat()
            candidates = conn.execute(
                f"""SELECT intent_id FROM order_intents
                    WHERE ticker=? AND action=? AND created_at>=? AND created_at<=?
                      AND state IN ({','.join('?' * len(_OPEN_STATES))})""",
                (ticker.upper(), action.lower(), cutoff, when.isoformat(),
                 *_OPEN_STATES),
            ).fetchall()
            if len(candidates) == 1:
                intent_id = candidates[0][0]
        cur = conn.execute(
            """INSERT INTO broker_order_receipts
               (intent_id, discord_message_id, received_at, outcome, broker,
                broker_group, account_last4, ticker, action, quantity, evidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                intent_id,
                None if discord_message_id is None else str(discord_message_id),
                when.isoformat(), outcome, broker, broker_group, account_last4,
                ticker.upper() if ticker else None, action.lower() if action else None,
                quantity, evidence[:500],
            ),
        )
        if intent_id and outcome == "accepted_reported":
            conn.execute(
                """UPDATE order_intents SET state='broker_accepted',
                       evidence_grade='legacy_text', updated_at=CURRENT_TIMESTAMP
                   WHERE intent_id=? AND state='dispatched'""",
                (intent_id,),
            )
        return int(cur.lastrowid)


def backfill_from_send_log(
    *, database: str | PathLike[str] | None = None
) -> int:
    """Create ``needs_review`` intents for send-log rows lacking one."""

    with _connect(database) as conn:
        rows = conn.execute(
            """SELECT s.send_id, s.sent_at, s.command, s.channel_id, s.ticker,
                      s.action, s.quantity, s.broker
               FROM rsa_order_send_log s
               LEFT JOIN order_intents i ON i.send_id = s.send_id
               WHERE i.intent_id IS NULL ORDER BY s.send_id"""
        ).fetchall()
    for r in rows:
        create_intent_for_send(
            r[0], created_at=r[1], command=r[2], channel_id=r[3], ticker=r[4],
            action=r[5], quantity=r[6], broker=r[7], source="send_log_backfill",
            database=database,
        )
    return len(rows)


def unverified_report(
    *, database: str | PathLike[str] | None = None
) -> list[dict[str, Any]]:
    """Intents with no broker-activity evidence, grouped by broker (read-only)."""

    with _connect(database) as conn:
        rows = conn.execute(
            """SELECT broker, state,
                      count(*), min(created_at), max(created_at),
                      sum(CASE WHEN EXISTS (SELECT 1 FROM broker_order_receipts r
                          WHERE r.intent_id=i.intent_id) THEN 1 ELSE 0 END)
               FROM order_intents i
               WHERE evidence_grade != 'broker_activity'
                 AND state NOT IN ('reconciled', 'cancelled')
               GROUP BY broker, state ORDER BY broker, state"""
        ).fetchall()
    return [
        {"broker": b, "state": st, "intents": n, "oldest": lo, "newest": hi,
         "with_receipt_text": rc}
        for b, st, n, lo, hi, rc in rows
    ]
