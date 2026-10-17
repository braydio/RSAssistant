#!/usr/bin/env python3
"""Read-only holdings parity report: auto-rsa JSON snapshot vs SQLite.

Prints per-broker account/position counts and freshness for the JSON snapshot,
``holdings_current`` and ``HoldingsLive``, plus recent ``holdings_import_log``
rows. Opens the database read-only; never prints account numbers.

    python scripts/holdings_reconcile.py --db volumes/db/rsa_database.db \
        --snapshot volumes/db/auto_rsa_holdings.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def snapshot_summary(path: Path) -> dict[str, dict]:
    """Summarise a snapshot in either flat-list or nested ``brokers`` form."""
    payload = json.loads(path.read_text())
    accounts: dict[str, set] = defaultdict(set)
    positions: dict[str, int] = defaultdict(int)
    if isinstance(payload, dict) and isinstance(payload.get("brokers"), dict):
        for broker, groups in payload["brokers"].items():
            for group, accts in groups.items():
                for acct, holdings in accts.items():
                    accounts[broker.lower()].add((group, acct))
                    positions[broker.lower()] += sum(
                        1 for k, v in holdings.items()
                        if not k.startswith("_") and isinstance(v, dict)
                    )
    else:
        entries = payload if isinstance(payload, list) else (
            next((payload[k] for k in ("holdings", "rows", "entries")
                  if isinstance(payload.get(k), list)), [])
        )
        for e in entries:
            if isinstance(e, dict) and e.get("broker") and e.get("ticker"):
                b = str(e["broker"]).lower()
                accounts[b].add((str(e.get("group", "1")), str(e.get("account", ""))))
                positions[b] += 1
    return {b: {"accounts": len(accounts[b]), "positions": positions[b]} for b in accounts}


def db_summary(conn: sqlite3.Connection, table: str, ts: str) -> dict[str, dict]:
    rows = conn.execute(
        f"SELECT lower(a.broker), count(DISTINCT t.account_id), count(*), max(t.{ts}) "
        f"FROM {table} t JOIN Accounts a USING(account_id) GROUP BY 1"
    ).fetchall()
    return {b: {"accounts": a, "positions": p, "latest": m} for b, a, p, m in rows}


def build_report(db: Path, snapshot: Path) -> dict:
    snap = snapshot_summary(snapshot)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cur = db_summary(conn, "holdings_current", "observed_at")
        live = db_summary(conn, "HoldingsLive", "timestamp") if _has_ts(conn) else {}
        log = conn.execute(
            "SELECT attempted_at, status, record_count, account_count, substr(source_sha256,1,12), error "
            "FROM holdings_import_log ORDER BY import_id DESC LIMIT 5"
        ).fetchall() if _has_table(conn, "holdings_import_log") else []
    finally:
        conn.close()
    brokers = sorted(set(snap) | set(cur) | set(live))
    rows = []
    for b in brokers:
        s, c = snap.get(b), cur.get(b)
        rows.append({
            "broker": b,
            "snapshot": s,
            "holdings_current": c,
            "holdings_live_latest": (live.get(b) or {}).get("latest"),
            "accounts_match": bool(s and c and s["accounts"] == c["accounts"]),
            "positions_match": bool(s and c and s["positions"] == c["positions"]),
        })
    mtime = datetime.fromtimestamp(snapshot.stat().st_mtime, timezone.utc).isoformat()
    return {"snapshot_mtime": mtime, "brokers": rows, "recent_imports": log}


def _has_table(conn, name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone())


def _has_ts(conn):
    return _has_table(conn, "HoldingsLive") and any(
        r[1] == "timestamp" for r in conn.execute("PRAGMA table_info(HoldingsLive)")
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--snapshot", required=True, type=Path)
    args = ap.parse_args(argv)
    report = build_report(args.db, args.snapshot)
    print(json.dumps(report, indent=2, default=str))
    return 0 if all(
        r["accounts_match"] and r["positions_match"]
        for r in report["brokers"] if r["snapshot"]
    ) else 2


if __name__ == "__main__":
    sys.exit(main())
