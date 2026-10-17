#!/usr/bin/env python3
"""One-screen, read-only operator status from the canonical SQLite DB.

Shows schema version, per-broker holdings freshness, recent snapshot imports,
open broker incidents, order intents lacking broker evidence, and open split
watches. Never prints account numbers; never writes.

    python scripts/operator_status.py --db volumes/db/rsa_database.db
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def q(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, type=Path)
    args = ap.parse_args(argv)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    out = []
    out.append(f"schema_version: {conn.execute('PRAGMA user_version').fetchone()[0]}")

    rows = q(conn, "SELECT lower(a.broker), count(DISTINCT h.account_id), count(*), max(h.observed_at) "
                   "FROM holdings_current h JOIN Accounts a USING(account_id) GROUP BY 1 ORDER BY 1")
    out.append("\nholdings_current (accounts / positions / newest):")
    for b, n, p, m in rows or []:
        out.append(f"  {b:<12} {n:>3} {p:>5}  {m}")

    rows = q(conn, "SELECT attempted_at, status, record_count, account_count, coalesce(error,'') "
                   "FROM holdings_import_log ORDER BY import_id DESC LIMIT 3")
    out.append("\nrecent snapshot imports:" + ("  (none / table absent)" if not rows else ""))
    for r in rows or []:
        out.append(f"  {r[0]} {r[1]} records={r[2]} accounts={r[3]} {r[4][:60]}")

    rows = q(conn, "SELECT level, profile, error_class, severity, occurrences FROM broker_incidents "
                   "WHERE status='open' ORDER BY (severity='critical') DESC")
    out.append("\nopen broker incidents:" + ("  (none / table absent)" if not rows else ""))
    for r in rows or []:
        out.append(f"  [{r[3]}] {r[0]}/{r[1]} {r[2]} x{r[4]}")

    rows = q(conn, "SELECT broker, state, count(*) FROM order_intents "
                   "WHERE evidence_grade!='broker_activity' AND state NOT IN ('reconciled','cancelled') "
                   "GROUP BY 1,2 ORDER BY 3 DESC")
    out.append("\norder intents without broker-activity evidence:" + ("  (none / table absent)" if not rows else ""))
    for b, s, n in rows or []:
        out.append(f"  {b:<28} {s:<16} {n}")

    rows = q(conn, "SELECT ticker, status FROM split_monitor ORDER BY ticker")
    out.append("\nsplit watches: " + (", ".join(f"{t}({s})" for t, s in rows) if rows else "none"))

    last = q(conn, "SELECT max(timestamp) FROM OrderHistory")
    out.append(f"\nOrderHistory newest row: {last[0][0] if last else 'n/a'}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
