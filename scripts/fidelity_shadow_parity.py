#!/usr/bin/env python3
"""Read-only parity: Fidelity snapshot adapter vs ``holdings_current`` (redacted)."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rsassistant.integrations.brokers.fidelity.adapter import (  # noqa: E402
    FidelitySnapshotAdapter, compare_positions)
from rsassistant.persistence.account_identity import account_forms, normalize_group  # noqa: E402
from rsassistant.services.broker_protocol import Operation, Request  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--snapshot", required=True, type=Path)
    args = ap.parse_args(argv)
    adapter = FidelitySnapshotAdapter(args.snapshot)
    shadow = adapter.handle(Request(Operation.POSITIONS, "parity"))["positions"]
    norm = lambda g, a: (normalize_group(g), account_forms(a)[0])  # noqa: E731
    a = [{"group": norm(p["group"], p["account"])[0], "account": norm(p["group"], p["account"])[1],
          "ticker": p["ticker"], "quantity": p["quantity"]} for p in shadow]
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT a.broker_number, a.account_number, h.ticker, h.quantity "
            "FROM holdings_current h JOIN Accounts a USING(account_id) "
            "WHERE lower(a.broker)='fidelity'").fetchall()
    finally:
        conn.close()
    b = [{"group": normalize_group(g), "account": account_forms(n)[0],
          "ticker": t.upper(), "quantity": q} for g, n, t, q in rows]
    report = compare_positions(a, b)
    print(json.dumps(report, indent=1))
    return 0 if report["match"] else 2


if __name__ == "__main__":
    sys.exit(main())
