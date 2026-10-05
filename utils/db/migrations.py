"""Compatibility imports for canonical persistence schema migrations."""

from rsassistant.persistence.schema import LATEST_SCHEMA_VERSION, run_migrations

__all__ = ["LATEST_SCHEMA_VERSION", "run_migrations"]
