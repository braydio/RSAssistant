"""Validated operator queries over the runtime SQLite database."""

from __future__ import annotations

import logging
import sqlite3
from os import PathLike

from rsassistant.persistence.db import connect_runtime_db
from utils.config_utils import SQL_DATABASE

logger = logging.getLogger(__name__)
DATABASE_PATH = SQL_DATABASE


def query_table(table_name, filters=None, order_by=None, limit=10, *, database=None):
    """Query a table and return rows or a descriptive error mapping."""
    logger.info(
        "Querying table %s with filters: %s, order_by: %s, limit: %s.",
        table_name,
        filters,
        order_by,
        limit,
    )
    with connect_runtime_db(database or DATABASE_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            valid_tables = [row[0] for row in cursor.fetchall()]
            if table_name not in valid_tables:
                logger.error("Invalid table: %s. Available tables: %s", table_name, valid_tables)
                return {"error": f"Invalid table name. Available tables: {valid_tables}"}

            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [row[1] for row in cursor.fetchall()]
            query = f"SELECT * FROM {table_name}"
            params = []
            if filters:
                conditions = []
                for key, value in filters.items():
                    if key not in columns:
                        logger.warning("Invalid filter column: %s. Available columns: %s", key, columns)
                        return {"error": f"Invalid filter column: {key}. Available columns: {columns}"}
                    conditions.append(f"{key} = ?")
                    params.append(value)
                query += " WHERE " + " AND ".join(conditions)
            if order_by and order_by in columns:
                query += f" ORDER BY {order_by}"
            if limit:
                query += f" LIMIT {limit}"
            logger.debug("Executing query: %s with params: %s", query, params)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            logger.info("Query executed successfully. Retrieved %s rows.", len(rows))
            return {"data": rows, "columns": columns}
        except sqlite3.Error as exc:
            logger.error("Database query error: %s", exc)
            return {"error": str(exc)}


__all__ = ["query_table"]
