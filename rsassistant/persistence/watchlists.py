"""Watchlist and sell-list persistence, including legacy JSON import."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

from rsassistant.persistence.db import connect_runtime_db
from utils.config_utils import ACCOUNT_MAPPING, SELL_FILE, SQL_DATABASE, WATCH_FILE
from rsassistant.persistence import accounts

logger = logging.getLogger(__name__)
DATABASE_PATH = SQL_DATABASE


def _get_db_connection(database=None):
    return connect_runtime_db(database or DATABASE_PATH)


def _parse_metadata(metadata: str | None) -> dict:
    if not metadata:
        return {}
    try:
        return json.loads(metadata)
    except json.JSONDecodeError:
        logger.warning("Failed to parse metadata JSON; returning empty dict.")
        return {}


def _serialize_metadata(metadata: dict | None) -> str:
    return json.dumps(metadata or {}, ensure_ascii=False)


def fetch_watchlist_entries(*, database=None) -> dict[str, dict[str, str]]:
    """Return watchlist entries keyed by ticker."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT ticker, split_date, split_ratio, metadata
                FROM watchlist
                ORDER BY ticker
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading watchlist: %s", exc)
            return {}

    watchlist: dict[str, dict[str, str]] = {}
    for ticker, split_date, split_ratio, metadata in rows:
        entry = {
            "split_date": split_date,
            "split_ratio": split_ratio or "N/A",
        }
        entry.update(_parse_metadata(metadata))
        watchlist[ticker.upper()] = entry

    return watchlist


def upsert_watchlist_entry(
    ticker: str,
    split_date: str,
    split_ratio: str,
    metadata: dict | None = None, *, database=None) -> bool:
    """Insert or update a watchlist entry."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO watchlist (
                ticker,
                split_date,
                split_ratio,
                metadata,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
            ON CONFLICT(ticker)
            DO UPDATE SET
                split_date = excluded.split_date,
                split_ratio = excluded.split_ratio,
                metadata = excluded.metadata,
                updated_at = DATETIME('now')
            """,
            (ticker.upper(), split_date, split_ratio, _serialize_metadata(metadata)),
        )
        conn.commit()
    return True


def delete_watchlist_entry(ticker: str, *, database=None) -> bool:
    """Remove a watchlist entry by ticker."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
        return cursor.rowcount > 0


def fetch_sell_list_entries(*, database=None) -> dict[str, dict[str, str]]:
    """Return sell list entries keyed by ticker."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT ticker, split_date, split_ratio, metadata
                FROM sell_list
                ORDER BY ticker
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading sell list: %s", exc)
            return {}

    sell_list: dict[str, dict[str, str]] = {}
    for ticker, split_date, split_ratio, metadata in rows:
        entry = _parse_metadata(metadata)
        if split_date:
            entry.setdefault("split_date", split_date)
        if split_ratio:
            entry.setdefault("split_ratio", split_ratio)
        sell_list[ticker.upper()] = entry

    return sell_list


def upsert_sell_list_entry(
    ticker: str,
    split_date: str | None = None,
    split_ratio: str | None = None,
    metadata: dict | None = None, *, database=None) -> bool:
    """Insert or update a sell list entry."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sell_list (
                ticker,
                split_date,
                split_ratio,
                metadata,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
            ON CONFLICT(ticker)
            DO UPDATE SET
                split_date = excluded.split_date,
                split_ratio = excluded.split_ratio,
                metadata = excluded.metadata,
                updated_at = DATETIME('now')
            """,
            (ticker.upper(), split_date, split_ratio, _serialize_metadata(metadata)),
        )
        conn.commit()
    return True


def delete_sell_list_entry(ticker: str, *, database=None) -> bool:
    """Remove a sell list entry by ticker."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sell_list WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
        return cursor.rowcount > 0


def fetch_watchlist_entry(ticker: str, *, database=None) -> dict[str, str] | None:
    """Return a single watchlist entry by ticker.

    Args:
        ticker: Symbol to fetch.

    Returns:
        Watchlist payload when present, otherwise ``None``.
    """

    return fetch_watchlist_entries(database=database).get(ticker.upper())


def replace_watchlist_entries(entries: dict[str, dict[str, str]], *, database=None) -> int:
    """Replace the entire watchlist table with ``entries``.

    Args:
        entries: Mapping keyed by ticker containing ``split_date`` and optional
            ``split_ratio`` plus metadata fields.

    Returns:
        Number of rows written.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist")
        for ticker, data in entries.items():
            payload = data if isinstance(data, dict) else {}
            metadata = {
                key: value
                for key, value in payload.items()
                if key not in {"split_date", "split_ratio"}
            }
            cursor.execute(
                """
                INSERT INTO watchlist (
                    ticker,
                    split_date,
                    split_ratio,
                    metadata,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
                """,
                (
                    ticker.upper(),
                    payload.get("split_date"),
                    payload.get("split_ratio", "N/A"),
                    _serialize_metadata(metadata or None),
                ),
            )
        conn.commit()
        return len(entries)


def fetch_sell_list_entry(ticker: str, *, database=None) -> dict[str, str] | None:
    """Return a single sell list entry by ticker."""

    return fetch_sell_list_entries(database=database).get(ticker.upper())


def replace_sell_list_entries(entries: dict[str, dict[str, str]], *, database=None) -> int:
    """Replace the entire sell list table with ``entries``.

    Args:
        entries: Mapping keyed by ticker that may include split metadata and
            scheduling fields.

    Returns:
        Number of rows written.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sell_list")
        for ticker, data in entries.items():
            payload = data if isinstance(data, dict) else {}
            cursor.execute(
                """
                INSERT INTO sell_list (
                    ticker,
                    split_date,
                    split_ratio,
                    metadata,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, DATETIME('now'), DATETIME('now'))
                """,
                (
                    ticker.upper(),
                    payload.get("split_date"),
                    payload.get("split_ratio"),
                    _serialize_metadata(payload),
                ),
            )
        conn.commit()
        return len(entries)


def _load_legacy_json(path: os.PathLike) -> dict:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            logger.warning("Legacy JSON %s is not a dict; skipping.", path)
            return {}
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed reading legacy JSON %s: %s", path, exc)
        return {}


def migrate_legacy_json_data(
    remove_legacy_files: bool = False, *, database=None,
    account_mapping_path=None, watch_file_path=None, sell_file_path=None,
) -> dict[str, int]:
    """Migrate legacy JSON mappings/watchlists into SQL tables.

    The migration is idempotent for populated SQL tables and only imports a
    legacy dataset when the corresponding table is empty.

    Args:
        remove_legacy_files: When ``True``, rename successfully imported legacy
            JSON files to ``*.migrated`` so they are no longer consumed.

    Returns:
        Mapping of migrated row counts for each dataset.
    """

    account_mapping_path = Path(account_mapping_path or ACCOUNT_MAPPING)
    watch_file_path = Path(watch_file_path or WATCH_FILE)
    sell_file_path = Path(sell_file_path or SELL_FILE)
    results = {"account_mappings": 0, "watchlist": 0, "sell_list": 0}

    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(1) FROM account_mappings")
            has_account_rows = cursor.fetchone()[0] > 0
            cursor.execute("SELECT COUNT(1) FROM watchlist")
            has_watch_rows = cursor.fetchone()[0] > 0
            cursor.execute("SELECT COUNT(1) FROM sell_list")
            has_sell_rows = cursor.fetchone()[0] > 0
        except sqlite3.Error as exc:
            logger.error("Failed checking legacy migration state: %s", exc)
            return results

    if not has_account_rows:
        legacy_mappings = _load_legacy_json(account_mapping_path)
        if legacy_mappings:
            sync_results = accounts.sync_account_mappings(legacy_mappings, database=database)
            results["account_mappings"] = (
                sync_results["added"] + sync_results["updated"]
            )

    if not has_watch_rows:
        legacy_watch = _load_legacy_json(watch_file_path)
        for ticker, data in legacy_watch.items():
            if isinstance(data, dict):
                split_date = data.get("split_date")
                split_ratio = data.get("split_ratio", "N/A")
            else:
                split_date = None
                split_ratio = "N/A"
            if split_date:
                upsert_watchlist_entry(
                    ticker=ticker,
                    split_date=split_date,
                    split_ratio=split_ratio,
                    metadata=None,
                    database=database,
                )
                results["watchlist"] += 1

    if not has_sell_rows:
        legacy_sell = _load_legacy_json(sell_file_path)
        for ticker, data in legacy_sell.items():
            metadata = data if isinstance(data, dict) else {}
            upsert_sell_list_entry(
                ticker=ticker,
                split_date=metadata.get("split_date"),
                split_ratio=metadata.get("split_ratio"),
                metadata=metadata,
                database=database,
            )
            results["sell_list"] += 1

    if any(results.values()):
        logger.info(
            "Legacy JSON migration complete. account_mappings=%s watchlist=%s sell_list=%s",
            results["account_mappings"],
            results["watchlist"],
            results["sell_list"],
        )
        if remove_legacy_files:
            for path in (account_mapping_path, watch_file_path, sell_file_path):
                try:
                    if os.path.exists(path):
                        os.replace(path, f"{path}.migrated")
                        logger.info("Archived legacy JSON file %s.migrated", path)
                except OSError as exc:
                    logger.warning(
                        "Failed to archive legacy JSON file %s: %s", path, exc
                    )
    return results
