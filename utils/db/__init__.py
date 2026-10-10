"""SQLite connection and schema migration helpers for RSAssistant."""

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import LATEST_SCHEMA_VERSION, run_migrations

connect_database = connect_runtime_db

__all__ = ["LATEST_SCHEMA_VERSION", "connect_database", "run_migrations"]
