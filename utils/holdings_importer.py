"""Helpers for importing holdings snapshots from external sources."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.config_utils import AUTO_RSA_HOLDINGS_FILE, AUTO_RSA_HOLDINGS_ENABLED
from rsassistant.persistence import holdings as holdings_repo
from utils.csv_utils import save_holdings_to_csv
from utils.logging_setup import logger
from utils.performance_metrics import timed_call


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


Fingerprint = tuple[int, int]

OUTCOME_CHANGED = "changed"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"

# Fingerprint (mtime_ns, size) of the last snapshot that was fully validated and
# persisted. Only advanced on success so failed imports are retried.
_last_import_fingerprint: Fingerprint | None = None
# Last fingerprint we already warned about, to avoid one warning per poll.
_last_failure_fingerprint: Fingerprint | None = None
_missing_warned = False


def _fingerprint(file_path: Path) -> Fingerprint:
    stat = file_path.stat()
    return (stat.st_mtime_ns, stat.st_size)


_last_recorded_failure: tuple[str, str] | None = None


def _record_import(
    file_path: Path,
    sha256: str | None,
    fingerprint: Fingerprint | None,
    entries: list[dict[str, Any]],
    status: str,
    error: str | None = None,
) -> None:
    """Persist snapshot identity/outcome; never lets bookkeeping break imports."""
    global _last_recorded_failure
    if status == "failed":
        key = (sha256 or "", error or "")
        if key == _last_recorded_failure:
            return
        _last_recorded_failure = key
    else:
        _last_recorded_failure = None
    mtime = (
        datetime.fromtimestamp(fingerprint[0] / 1e9, timezone.utc).isoformat()
        if fingerprint
        else None
    )
    try:
        holdings_repo.record_holdings_import(
            source_path=str(file_path),
            source_sha256=sha256,
            source_mtime=mtime,
            record_count=len(entries),
            account_count=len(
                {(e["broker"], e["group"], e["account"]) for e in entries}
            ),
            status=status,
            error=error,
        )
    except Exception as exc:  # bookkeeping only
        logger.warning("Could not record holdings import outcome: %s", exc)


def _import_snapshot(file_path: Path) -> tuple[str, int, Fingerprint | None]:
    """Import one snapshot. Returns ``(outcome, imported_count, fingerprint)``.

    The fingerprint is taken before and after the read; a mismatch means the
    file was being rewritten, so nothing is persisted.
    """

    try:
        before = _fingerprint(file_path)
        text = file_path.read_text()
        after = _fingerprint(file_path)
    except OSError as exc:
        logger.warning("Unable to read holdings file %s: %s", file_path, exc)
        return OUTCOME_FAILED, 0, None
    if before != after:
        logger.warning("Holdings file changed during read; will retry: %s", file_path)
        return OUTCOME_FAILED, 0, None

    sha256 = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()

    # Re-warn about the same unchanged bad snapshot only at DEBUG.
    warn = logger.debug if before == _last_failure_fingerprint else logger.warning
    try:
        payload = json.loads(text)
    except ValueError as exc:
        warn("Failed to parse holdings file %s: %s", file_path, exc)
        _record_import(file_path, sha256, before, [], "failed", f"parse error: {exc}")
        return OUTCOME_FAILED, 0, before

    normalized = []
    for entry in _extract_entries(payload):
        normalized_entry = _normalize_entry(entry)
        if normalized_entry:
            normalized.append(normalized_entry)

    if not normalized:
        warn("No valid holdings entries found in %s", file_path)
        _record_import(file_path, sha256, before, [], "failed", "no valid entries")
        return OUTCOME_FAILED, 0, before

    for holding in normalized:
        holding["Key"] = (
            f"{holding['broker']}_{holding['group']}_{holding['account']}_{holding['ticker']}"
        )

    try:
        saved = save_holdings_to_csv(normalized, use_refresh_target=False)
    except (OSError, ValueError, sqlite3.Error) as exc:
        warn("Failed to persist holdings from %s: %s", file_path, exc)
        _record_import(file_path, sha256, before, normalized, "failed", str(exc))
        return OUTCOME_FAILED, 0, before
    if saved is False:
        warn("Holdings from %s were not persisted (see save error above)", file_path)
        _record_import(
            file_path, sha256, before, normalized, "failed", "save_holdings_to_csv returned False"
        )
        return OUTCOME_FAILED, 0, before
    _record_import(file_path, sha256, before, normalized, "succeeded")
    logger.info("Imported %d holdings entries from %s", len(normalized), file_path)
    return OUTCOME_CHANGED, len(normalized), before


def import_holdings_file(path: Path | str | None = None) -> int:
    """Import holdings from a JSON snapshot file.

    Returns the number of holdings entries ingested.
    """

    if not AUTO_RSA_HOLDINGS_ENABLED:
        logger.debug("Auto-RSA holdings import disabled; skipping.")
        return 0

    file_path = Path(path or AUTO_RSA_HOLDINGS_FILE)
    if not file_path.exists():
        logger.warning("Holdings file missing: %s", file_path)
        return 0
    return _import_snapshot(file_path)[1]


def import_holdings_if_updated(path: Path | str | None = None) -> int:
    """Import holdings only when the snapshot file changes.

    The snapshot is acknowledged only after it was validated and persisted, so a
    failed or empty import is retried on the next poll.
    """
    global _last_import_fingerprint, _last_failure_fingerprint, _missing_warned
    if not AUTO_RSA_HOLDINGS_ENABLED:
        return 0
    file_path = Path(path or AUTO_RSA_HOLDINGS_FILE)
    try:
        fingerprint = _fingerprint(file_path)
    except FileNotFoundError:
        if not _missing_warned:
            logger.warning("Holdings file missing: %s", file_path)
            _missing_warned = True
        return 0
    except OSError:
        logger.warning("Unable to stat holdings file: %s", file_path)
        return 0
    _missing_warned = False

    if fingerprint == _last_import_fingerprint:
        return 0
    with timed_call("holdings_import"):
        outcome, imported, taken = _import_snapshot(file_path)
    if outcome == OUTCOME_CHANGED:
        _last_import_fingerprint = taken
        _last_failure_fingerprint = None
    else:
        _last_failure_fingerprint = fingerprint
    return imported
