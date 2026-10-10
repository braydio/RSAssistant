"""Compatibility facade for SQL persistence APIs.

Domain implementations live under :mod:`rsassistant.persistence`. New code
should import repositories directly; this module preserves older import paths
and patchable database/config constants for existing callers and tests.
"""

from __future__ import annotations

import logging
from functools import wraps

from rsassistant.persistence import accounts, admin, holdings, orders, reverse_splits, watchlists
from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import (
    ACCOUNT_MAPPING,
    CSV_LOGGING_ENABLED,
    SELL_FILE,
    SQL_DATABASE,
    SQL_LOGGING_ENABLED,
    WATCH_FILE,
)

logger = logging.getLogger(__name__)


def get_db_connection():
    """Return a connection to the configured runtime database."""
    return connect_runtime_db(SQL_DATABASE)


def _database_compat(function, *, paths=False):
    """Adapt legacy calls to repositories while honoring patched DB settings."""
    @wraps(function)
    def call(*args, **kwargs):
        kwargs.setdefault("database", SQL_DATABASE)
        if paths:
            kwargs.setdefault("account_mapping_path", ACCOUNT_MAPPING)
            kwargs.setdefault("watch_file_path", WATCH_FILE)
            kwargs.setdefault("sell_file_path", SELL_FILE)
        return function(*args, **kwargs)

    return call


for _name in (
    "get_or_create_account_id",
    "upsert_account_mapping",
    "sync_account_mappings",
    "clear_account_nicknames",
    "fetch_account_mappings",
    "fetch_account_nickname",
    "fetch_account_labels",
    "resolve_account_id",
    "has_account_mappings",
):
    globals()[_name] = _database_compat(getattr(accounts, _name))

for _name in (
    "fetch_watchlist_entries",
    "upsert_watchlist_entry",
    "delete_watchlist_entry",
    "fetch_sell_list_entries",
    "upsert_sell_list_entry",
    "delete_sell_list_entry",
    "fetch_watchlist_entry",
    "replace_watchlist_entries",
    "fetch_sell_list_entry",
    "replace_sell_list_entries",
):
    globals()[_name] = _database_compat(getattr(watchlists, _name))

migrate_legacy_json_data = _database_compat(
    watchlists.migrate_legacy_json_data, paths=True
)

for _name in (
    "insert_reverse_split_log_entry",
    "fetch_reverse_split_history",
    "insert_reverse_split_account_entry",
    "fetch_reverse_split_account_entries",
):
    globals()[_name] = _database_compat(getattr(reverse_splits, _name))

for _name in (
    "update_holdings_live",
    "update_holdings_live_batch",
    "update_historical_holdings",
):
    globals()[_name] = _database_compat(getattr(holdings, _name))


def init_db():
    """Initialize schemas and import configured legacy JSON data."""
    with get_db_connection() as connection:
        run_migrations(connection)
    migrate_legacy_json_data()


def replace_current_holdings_snapshot(holdings_rows, *, source="holdings_snapshot"):
    return holdings.replace_current_holdings(
        holdings_rows, source=source, database=SQL_DATABASE
    )


def stage_current_holdings_snapshot(
    refresh_id, holdings_rows, *, source="holdings_refresh"
):
    return holdings.stage_current_holdings(
        refresh_id, holdings_rows, source=source, database=SQL_DATABASE
    )


def activate_current_holdings_snapshot(refresh_id):
    return holdings.activate_staged_holdings(refresh_id, database=SQL_DATABASE)


def discard_current_holdings_snapshot(refresh_id):
    return holdings.discard_staged_holdings(refresh_id, database=SQL_DATABASE)


def get_current_holdings_snapshot():
    return holdings.get_current_holdings(database=SQL_DATABASE)


def validate_order_data(order_data):
    """Validate the historical normalized-order mapping contract."""
    required_fields = (
        "order_id", "account_id", "broker", "broker_name", "broker_number",
        "account_number", "ticker", "date", "action", "quantity", "price",
        "total_value",
    )
    for field in required_fields:
        if field not in order_data:
            raise ValueError(f"Missing required field in order_data: {field}")


def insert_order_history(order_data):
    """Compatibility entrypoint for legacy CSV-shaped order dictionaries."""
    orders.insert_order_event(
        order_data, database=SQL_DATABASE, export_csv=CSV_LOGGING_ENABLED
    )


def bot_query_database(table_name, filters=None, order_by=None, limit=10):
    """Compatibility delegate for validated operator table queries."""
    return admin.query_table(
        table_name, filters, order_by, limit, database=SQL_DATABASE
    )


__all__ = [
    "SQL_DATABASE",
    "SQL_LOGGING_ENABLED",
    "ACCOUNT_MAPPING",
    "WATCH_FILE",
    "SELL_FILE",
    "get_db_connection",
    "get_or_create_account_id",
    "upsert_account_mapping",
    "sync_account_mappings",
    "clear_account_nicknames",
    "fetch_account_mappings",
    "fetch_account_nickname",
    "fetch_account_labels",
    "resolve_account_id",
    "has_account_mappings",
    "fetch_watchlist_entries",
    "upsert_watchlist_entry",
    "delete_watchlist_entry",
    "fetch_sell_list_entries",
    "upsert_sell_list_entry",
    "delete_sell_list_entry",
    "fetch_watchlist_entry",
    "replace_watchlist_entries",
    "fetch_sell_list_entry",
    "replace_sell_list_entries",
    "migrate_legacy_json_data",
    "init_db",
    "insert_reverse_split_log_entry",
    "fetch_reverse_split_history",
    "insert_reverse_split_account_entry",
    "fetch_reverse_split_account_entries",
    "update_holdings_live",
    "update_holdings_live_batch",
    "replace_current_holdings_snapshot",
    "stage_current_holdings_snapshot",
    "activate_current_holdings_snapshot",
    "discard_current_holdings_snapshot",
    "get_current_holdings_snapshot",
    "update_historical_holdings",
    "validate_order_data",
    "insert_order_history",
    "bot_query_database",
]
