"""Shared SQLite connection configuration."""

import sqlite3
from os import PathLike


class ClosingConnection(sqlite3.Connection):
    """SQLite connection whose context manager also releases the handle."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect_database(database: str | PathLike[str]) -> sqlite3.Connection:
    """Open a connection with settings that SQLite applies per connection."""

    connection = sqlite3.connect(database, timeout=30, factory=ClosingConnection)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection
