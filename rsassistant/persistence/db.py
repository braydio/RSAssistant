"""Runtime SQLite connections and initialization."""

from __future__ import annotations

import sqlite3
from os import PathLike
from pathlib import Path

from rsassistant.persistence.schema import LATEST_SCHEMA_VERSION, run_migrations


class ClosingConnection(sqlite3.Connection):
    """SQLite connection whose context manager also releases the handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _database_path(database: str | PathLike[str] | None) -> str:
    if database is None:
        from utils.config_utils import SQL_DATABASE

        database = SQL_DATABASE

    path = str(database)
    if path != ":memory:":
        Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return path


def connect_runtime_db(
    database: str | PathLike[str] | None = None,
) -> sqlite3.Connection:
    """Open the configured SQLite runtime database with shared pragmas."""

    connection = sqlite3.connect(
        _database_path(database), timeout=30, factory=ClosingConnection
    )
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_runtime_db(database: str | PathLike[str] | None = None) -> int:
    """Apply pending schema migrations and return the current schema version."""

    with connect_runtime_db(database) as connection:
        return run_migrations(connection)


__all__ = [
    "ClosingConnection",
    "LATEST_SCHEMA_VERSION",
    "connect_runtime_db",
    "initialize_runtime_db",
    "run_migrations",
]
