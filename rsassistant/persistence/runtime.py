"""Runtime database initialization and one-time legacy imports."""

from __future__ import annotations

from os import PathLike

from rsassistant.persistence.db import initialize_runtime_db
from rsassistant.persistence.watchlists import migrate_legacy_json_data


def initialize_runtime(database: str | PathLike[str] | None = None) -> dict[str, int]:
    """Apply schema migrations, then import configured legacy JSON state."""
    initialize_runtime_db(database)
    return migrate_legacy_json_data(database=database)


__all__ = ["initialize_runtime"]
