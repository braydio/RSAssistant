"""Compatibility imports for the canonical SQLite connection helper."""

from rsassistant.persistence.db import ClosingConnection, connect_runtime_db

connect_database = connect_runtime_db

__all__ = ["ClosingConnection", "connect_database"]
