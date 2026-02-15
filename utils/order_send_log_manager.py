"""Persistent audit log helpers for sent ``!rsa`` commands."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.config_utils import VOLUMES_DIR

ORDER_SEND_LOG_FILE: Path = VOLUMES_DIR / "db" / "order_send_log.json"
_MAX_ENTRIES = 1000

ORDER_SEND_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_send_log() -> list[dict[str, Any]]:
    """Load sent-order entries from disk.

    Returns:
        List of send-log dictionaries sorted by append order.
    """

    if not ORDER_SEND_LOG_FILE.exists():
        return []
    with ORDER_SEND_LOG_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, list) else []


def _save_send_log(entries: list[dict[str, Any]]) -> None:
    """Persist sent-order entries to disk."""

    with ORDER_SEND_LOG_FILE.open("w", encoding="utf-8") as file:
        json.dump(entries, file, indent=2)


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
    """Append an audit record for an outbound ``!rsa`` command.

    Args:
        command: Full outbound command string.
        channel_id: Discord channel identifier where the command was sent.
        ticker: Ticker symbol associated with the order.
        action: Normalized action (buy/sell).
        quantity: Submitted quantity value.
        broker: Target broker token.
        sent_at: Optional timestamp override, defaults to current UTC.

    Returns:
        The entry dictionary that was written.
    """

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

    entries = _load_send_log()
    entries.append(entry)
    if len(entries) > _MAX_ENTRIES:
        entries = entries[-_MAX_ENTRIES:]
    _save_send_log(entries)
    return entry


def list_sent_rsa_orders(
    *, limit: int = 10, ticker: str | None = None, action: str | None = None
) -> list[dict[str, Any]]:
    """Return most-recent sent ``!rsa`` audit entries.

    Args:
        limit: Maximum number of entries to return.
        ticker: Optional ticker filter.
        action: Optional order-action filter.

    Returns:
        Most-recent matching entries in descending send-time order.
    """

    entries = _load_send_log()
    if ticker:
        ticker_filter = ticker.upper()
        entries = [entry for entry in entries if entry.get("ticker") == ticker_filter]
    if action:
        action_filter = action.lower()
        entries = [entry for entry in entries if entry.get("action") == action_filter]

    if limit <= 0:
        return []
    return list(reversed(entries[-limit:]))


def latest_sent_rsa_order(ticker: str | None = None) -> dict[str, Any] | None:
    """Return the latest sent ``!rsa`` entry, optionally constrained by ticker."""

    entries = list_sent_rsa_orders(limit=1, ticker=ticker)
    return entries[0] if entries else None
