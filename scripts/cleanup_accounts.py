#!/usr/bin/env python3
"""Audit and prune the ``Accounts`` table.

Dry-run by default: prints counts only (no account numbers). With ``--apply``
it removes (1) test-fixture accounts and the pytest row left in
``holdings_current``, and (2) accounts that have no rows in any child table and
are absent from the live auto-rsa snapshot. A consistent backup of the database
is written first. Accounts that still own order or holdings history are never
deleted here.

Usage::

    python scripts/cleanup_accounts.py [--db PATH] [--snapshot PATH] [--apply]
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHILD_TABLES = (
    "HistoricalHoldings",
    "OrderHistory",
    "HoldingsLive",
    "ReverseSplitAccountEntries",
    "holdings_current",
    "holdings_refresh_staging",
    "account_value_snapshots",
)
TEST_BROKERS = ("B", "BROKERA")


def canonical_key(broker, broker_number, account_number):
    """Identity that ignores broker casing and number-label conventions."""
    match = re.search(r"(\d+)\s*$", str(broker_number))
    number = match.group(1) if match else str(broker_number)
    return (str(broker).upper(), number, str(account_number)[-4:])


def snapshot_keys(path: Path) -> set[tuple[str, str, str]]:
    entries = json.loads(path.read_text())
    return {
        canonical_key(e["broker"], e.get("group", "1"), e["account"])
        for e in entries
        if isinstance(e, dict) and e.get("broker") and e.get("account")
    }


def plan(conn: sqlite3.Connection, live: set) -> tuple[list[int], list[int]]:
    placeholders = ",".join("?" * len(TEST_BROKERS))
    test_ids = [
        r[0]
        for r in conn.execute(
            f"SELECT account_id FROM Accounts WHERE upper(broker) IN ({placeholders})",
            TEST_BROKERS,
        )
    ]
    empty = []
    for account_id, broker, number, account in conn.execute(
        "SELECT account_id, broker, broker_number, account_number FROM Accounts"
    ).fetchall():
        if account_id in test_ids or canonical_key(broker, number, account) in live:
            continue
        has_data = any(
            conn.execute(
                f"SELECT 1 FROM {table} WHERE account_id=? LIMIT 1", (account_id,)
            ).fetchone()
            for table in CHILD_TABLES
        )
        if not has_data:
            empty.append(account_id)
    return test_ids, empty


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=ROOT / "volumes/db/rsa_database.db")
    parser.add_argument(
        "--snapshot", type=Path, default=ROOT / "volumes/db/auto_rsa_holdings.json"
    )
    parser.add_argument("--apply", action="store_true", help="perform the deletions")
    args = parser.parse_args(argv)

    live = snapshot_keys(args.snapshot)
    conn = sqlite3.connect(args.db, timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    total = conn.execute("SELECT count(*) FROM Accounts").fetchone()[0]
    test_ids, empty = plan(conn, live)
    by_broker = collections.Counter(
        conn.execute("SELECT upper(broker) FROM Accounts WHERE account_id=?", (i,)).fetchone()[0]
        for i in empty
    )
    pytest_rows = conn.execute(
        "SELECT count(*) FROM holdings_current WHERE source LIKE '/tmp/pytest-of-%'"
    ).fetchone()[0]
    print(f"Accounts: {total}; live snapshot identities: {len(live)}")
    print(f"test-fixture accounts: {len(test_ids)}; pytest holdings_current rows: {pytest_rows}")
    print(f"data-less accounts not in snapshot: {len(empty)} {dict(by_broker)}")
    if not args.apply:
        print("dry run: nothing changed (use --apply)")
        return 0

    backup = args.db.with_name(
        f"{args.db.name}.bak-{datetime.now():%Y%m%d-%H%M%S}-pre-account-cleanup"
    )
    shutil.copy2(args.db, backup)
    print(f"backup: {backup}")
    conn.execute("BEGIN IMMEDIATE")
    for account_id in test_ids:
        for table in CHILD_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE account_id=?", (account_id,))
    conn.execute("DELETE FROM holdings_current WHERE source LIKE '/tmp/pytest-of-%'")
    for account_id in (*test_ids, *empty):
        conn.execute("DELETE FROM Accounts WHERE account_id=?", (account_id,))
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        conn.rollback()
        print(f"aborted: {len(violations)} foreign-key violations", file=sys.stderr)
        return 1
    conn.commit()
    print(f"Accounts now: {conn.execute('SELECT count(*) FROM Accounts').fetchone()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
