"""Helpers for importing holdings snapshots from external sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.config_utils import AUTO_RSA_HOLDINGS_FILE, AUTO_RSA_HOLDINGS_ENABLED
from utils.csv_utils import save_holdings_to_csv
from utils.logging_setup import logger


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    broker = str(entry.get("broker", "")).strip()
    group = str(entry.get("group", "")).strip()
    account = str(entry.get("account", "")).strip()
    ticker = str(entry.get("ticker", "")).strip()
    if not (broker and account and ticker):
        return None

    return {
        "broker": broker,
        "group": group or "1",
        "account": account,
        "ticker": ticker,
        "quantity": entry.get("quantity", 0),
        "price": entry.get("price", 0),
        "value": entry.get("value", 0),
        "account_total": entry.get("account_total", 0),
        "account_name": entry.get("account_name")
        or f"{broker} {group or '1'} {account}",
    }


def _expand_nested_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    brokers = payload.get("brokers")
    if not isinstance(brokers, dict):
        return entries

    for broker_name, groups in brokers.items():
        if not isinstance(groups, dict):
            continue
        for group_number, accounts in groups.items():
            if not isinstance(accounts, dict):
                continue
            for account_number, holdings in accounts.items():
                if not isinstance(holdings, dict):
                    continue
                account_total = holdings.get("account_total")
                if account_total is None and "_account_total" in holdings:
                    account_total = holdings.get("_account_total")
                for ticker, detail in holdings.items():
                    if ticker.startswith("_"):
                        continue
                    if not isinstance(detail, dict):
                        continue
                    entries.append(
                        {
                            "broker": broker_name,
                            "group": group_number,
                            "account": account_number,
                            "ticker": ticker,
                            "quantity": detail.get("quantity", 0),
                            "price": detail.get("price", 0),
                            "value": detail.get("total", detail.get("value", 0)),
                            "account_total": account_total or 0,
                        }
                    )

    return entries


def _extract_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]

    if isinstance(payload, dict):
        for key in ("holdings", "rows", "entries"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [entry for entry in candidate if isinstance(entry, dict)]
        nested_entries = _expand_nested_payload(payload)
        if nested_entries:
            return nested_entries

    return []


_last_import_mtime: float | None = None


def import_holdings_file(path: Path | str | None = None) -> int:
    """Import holdings from a JSON snapshot file.

    Returns the number of holdings entries ingested.
    """

    if not AUTO_RSA_HOLDINGS_ENABLED:
        logger.info("Auto-RSA holdings import disabled; skipping.")
        return 0

    file_path = Path(path or AUTO_RSA_HOLDINGS_FILE)
    if not file_path.exists():
        return 0

    try:
        payload = json.loads(file_path.read_text())
    except Exception as exc:
        logger.warning("Failed to parse holdings file %s: %s", file_path, exc)
        return 0

    entries = _extract_entries(payload)
    normalized = []
    for entry in entries:
        normalized_entry = _normalize_entry(entry)
        if normalized_entry:
            normalized.append(normalized_entry)

    if not normalized:
        logger.info("No holdings entries found in %s", file_path)
        return 0

    for holding in normalized:
        holding["Key"] = (
            f"{holding['broker']}_{holding['group']}_{holding['account']}_{holding['ticker']}"
        )

    save_holdings_to_csv(normalized)
    logger.info("Imported %d holdings entries from %s", len(normalized), file_path)
    return len(normalized)


def import_holdings_if_updated(path: Path | str | None = None) -> int:
    """Import holdings only when the snapshot file changes."""
    global _last_import_mtime
    if not AUTO_RSA_HOLDINGS_ENABLED:
        return 0
    file_path = Path(path or AUTO_RSA_HOLDINGS_FILE)
    if not file_path.exists():
        return 0
    try:
        mtime = file_path.stat().st_mtime
    except OSError:
        return 0
    if _last_import_mtime is not None and mtime <= _last_import_mtime:
        return 0
    imported = import_holdings_file(file_path)
    _last_import_mtime = mtime
    return imported
