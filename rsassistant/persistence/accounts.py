"""Account identity and nickname persistence."""

from __future__ import annotations

import logging
import sqlite3

from rsassistant.persistence.db import connect_runtime_db
from utils.config_utils import SQL_DATABASE, get_account_nickname_or_default

logger = logging.getLogger(__name__)
DATABASE_PATH = SQL_DATABASE


def _get_db_connection(database=None):
    return connect_runtime_db(database or DATABASE_PATH)


def get_or_create_account_id(
    broker, broker_number, account_number, account_nickname=None, *, database=None):
    """
    Retrieve or create an account entry.

    Returns ``None`` when SQL logging is disabled. If ``account_nickname``
    is ``None`` the nickname is resolved using
    :func:`utils.config_utils.get_account_nickname_or_default`.
    """
    logger.info(
        f"Fetching or creating account ID for broker: {broker}, broker_number: {broker_number}, account_number: {account_number}."
    )


    nickname_was_explicit = account_nickname is not None
    if account_nickname is None:
        account_nickname = get_account_nickname_or_default(
            broker, broker_number, account_number
        )

    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO Accounts (broker, account_number, broker_number, account_nickname)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(broker, broker_number, account_number) DO NOTHING
                RETURNING account_id
                """,
                (broker, account_number, broker_number, account_nickname),
            )
            row = cursor.fetchone()
            if row:
                account_id = int(row[0])
            else:
                cursor.execute(
                    """SELECT account_id FROM Accounts
                       WHERE broker=? AND broker_number=? AND account_number=?""",
                    (broker, broker_number, account_number),
                )
                account_id = int(cursor.fetchone()[0])
                if nickname_was_explicit:
                    cursor.execute(
                        """UPDATE Accounts SET account_nickname=?,
                               updated_at=DATETIME('now') WHERE account_id=?""",
                        (account_nickname, account_id),
                    )
            logger.debug("Resolved account ID: %s.", account_id)
            return account_id
        except sqlite3.Error as e:
            logger.error(f"Error retrieving or creating account_id: {e}")
            raise


def upsert_account_mapping(
    broker: str, broker_number: str, account_number: str, account_nickname: str, *, database=None) -> bool:
    """Insert or update account nickname mappings in SQL storage.

    Args:
        broker: Broker name for the account.
        broker_number: Broker group identifier.
        account_number: Account identifier.
        account_nickname: Friendly nickname to store.

    Returns:
        ``True`` when SQL storage was updated, ``False`` when SQL logging is
        disabled.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Accounts (
                broker, broker_number, account_number, account_nickname
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(broker, broker_number, account_number) DO UPDATE SET
                account_nickname = excluded.account_nickname,
                updated_at = DATETIME('now')
            """,
            (broker, broker_number, account_number, account_nickname),
        )
        conn.commit()
        logger.info(
            "Upserted SQL account nickname for %s/%s/%s.",
            broker,
            broker_number,
            account_number,
        )
        return True


def sync_account_mappings(mappings: dict, *, database=None) -> dict[str, int]:
    """Synchronize a JSON mapping dictionary into SQL storage.

    Args:
        mappings: Nested broker/group/account mapping structure.

    Returns:
        Dictionary with ``added`` and ``updated`` counts.
    """

    results = {"added": 0, "updated": 0}

    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        for broker, broker_groups in mappings.items():
            for broker_number, accounts in broker_groups.items():
                for account_number, nickname in accounts.items():
                    cursor.execute(
                        """
                        SELECT account_nickname
                        FROM Accounts
                        WHERE broker = ? AND broker_number = ? AND account_number = ?
                        """,
                        (broker, broker_number, account_number),
                    )
                    row = cursor.fetchone()
                    if row:
                        if row[0] != nickname:
                            cursor.execute(
                                """
                                UPDATE Accounts
                                SET account_nickname = ?, updated_at = DATETIME('now')
                                WHERE broker = ? AND broker_number = ? AND account_number = ?
                                """,
                                (nickname, broker, broker_number, account_number),
                            )
                            results["updated"] += 1
                    else:
                        cursor.execute(
                            """
                            INSERT INTO Accounts (
                                broker, broker_number, account_number, account_nickname
                            ) VALUES (?, ?, ?, ?)
                            """,
                            (broker, broker_number, account_number, nickname),
                        )
                        results["added"] += 1

        conn.commit()

    logger.info(
        "Synced account mappings to SQL. Added=%s Updated=%s",
        results["added"],
        results["updated"],
    )
    return results


def clear_account_nicknames(*, database=None) -> int:
    """Clear stored account nicknames from SQL storage.

    Returns:
        Number of rows updated.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Accounts SET account_nickname = NULL")
        cleared = cursor.rowcount
        conn.commit()
        logger.info("Cleared account nicknames in SQL storage.")
        return cleared


def fetch_account_mappings(*, database=None) -> dict[str, dict[str, dict[str, str]]]:
    """Return account mappings stored in SQL.

    Returns:
        Nested mapping ``{broker: {broker_number: {account_number: nickname}}}``.
    """


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT broker, broker_number, account_number, account_nickname
                FROM Accounts
                WHERE account_nickname IS NOT NULL
                ORDER BY broker, broker_number, account_number
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading account mappings: %s", exc)
            return {}

    mappings: dict[str, dict[str, dict[str, str]]] = {}
    for broker, broker_number, account_number, nickname in rows:
        if nickname is None:
            continue
        mappings.setdefault(broker, {}).setdefault(str(broker_number), {})[
            str(account_number)
        ] = nickname

    return mappings


def fetch_account_nickname(
    broker: str, broker_number: str, account_number: str, *, database=None) -> str | None:
    """Return the nickname for an account from SQL."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT account_nickname
                FROM Accounts
                WHERE broker = ? AND broker_number = ? AND account_number = ?
                """,
                (broker, broker_number, account_number),
            )
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            logger.error("Failed reading account nickname: %s", exc)
            return None
    return row[0] if row else None


def fetch_account_labels(*, database=None) -> list[dict[str, str]]:
    """Return account IDs and nicknames from the Accounts table."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT account_id, account_nickname
                FROM Accounts
                WHERE account_nickname IS NOT NULL
                """
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            logger.error("Failed reading account labels: %s", exc)
            return []

    return [
        {"account_id": row[0], "account_nickname": row[1]} for row in rows if row[1]
    ]


def resolve_account_id(account_input: str, *, database=None) -> int | None:
    """Resolve a numeric account ID or nickname to one integer account ID."""

    for entry in fetch_account_labels(database=database):
        if account_input.isdigit() and str(entry["account_id"]) == account_input:
            return int(entry["account_id"])
        if entry["account_nickname"].lower() == account_input.lower():
            return int(entry["account_id"])
    return None


def has_account_mappings(*, database=None) -> bool:
    """Return ``True`` when SQL has at least one account mapping row."""


    with _get_db_connection(database) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COUNT(1) FROM Accounts WHERE account_nickname IS NOT NULL"
            )
            count = cursor.fetchone()[0]
        except sqlite3.Error as exc:
            logger.error("Failed checking account mappings: %s", exc)
            return False
    return count > 0
