"""Canonical runtime persistence layer for RSAssistant."""

from rsassistant.persistence.db import connect_runtime_db, initialize_runtime_db
from rsassistant.persistence.holdings import (
    activate_staged_holdings,
    discard_staged_holdings,
    get_current_holdings,
    replace_current_holdings,
    stage_current_holdings,
)
from rsassistant.persistence.schema import LATEST_SCHEMA_VERSION, run_migrations

__all__ = [
    "LATEST_SCHEMA_VERSION",
    "activate_staged_holdings",
    "connect_runtime_db",
    "discard_staged_holdings",
    "get_current_holdings",
    "initialize_runtime_db",
    "replace_current_holdings",
    "run_migrations",
    "stage_current_holdings",
]
