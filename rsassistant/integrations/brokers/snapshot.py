"""Read-only broker adapter backed by the auto-rsa holdings snapshot (any broker).

This is the *shadow* implementation: it exposes the agreed ``BrokerAdapter``
operations from the legacy JSON output so the typed bridge and parity tooling
can be exercised without a browser session. Live adapters are separate, human-gated steps.

Capabilities: ``list_accounts``, ``positions``, ``health``. ``submit_order``,
``get_order`` and ``activities`` are deliberately unsupported -- there is no
authoritative broker order confirmation source here, and success is never
inferred from a click.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rsassistant.services.broker_protocol import Operation, Request


def _mask(account: str) -> str:
    text = str(account)
    return "*" * max(len(text) - 4, 0) + text[-4:]


class SnapshotBrokerAdapter:
    capabilities = frozenset({Operation.LIST_ACCOUNTS, Operation.POSITIONS, Operation.HEALTH})

    def __init__(self, snapshot_path: str | Path, *, broker_name: str):
        self.path = Path(snapshot_path)
        self.broker_name = broker_name.lower()

    def _entries(self) -> list[dict[str, Any]]:
        data = json.loads(self.path.read_text())
        if isinstance(data, dict):
            data = next((data[k] for k in ("holdings", "rows", "entries")
                         if isinstance(data.get(k), list)), [])
        return [e for e in data if isinstance(e, dict)
                and str(e.get("broker", "")).lower() == self.broker_name]

    def handle(self, request: Request) -> dict[str, Any]:
        if request.op is Operation.HEALTH:
            mtime = datetime.fromtimestamp(self.path.stat().st_mtime, timezone.utc)
            return {"status": "healthy" if self.path.exists() else "unknown",
                    "snapshot_at": mtime.isoformat(), "mode": "snapshot_shadow"}
        entries = self._entries()
        if request.op is Operation.LIST_ACCOUNTS:
            accounts = sorted({(str(e.get("group", "1")), str(e["account"])) for e in entries})
            return {"accounts": [{"group": g, "account": a} for g, a in accounts]}
        if request.op is Operation.POSITIONS:
            want = request.params.get("account")
            return {"positions": [
                {"group": str(e.get("group", "1")), "account": str(e["account"]),
                 "ticker": str(e["ticker"]).upper(), "quantity": float(e.get("quantity", 0))}
                for e in entries if want is None or str(e["account"]) == str(want)
            ]}
        raise NotImplementedError(request.op.value)


def compare_positions(
    a: list[dict[str, Any]], b: list[dict[str, Any]], *, tolerance: float = 1e-6
) -> dict[str, Any]:
    """Diff two position sets. Account ids are redacted in the output."""
    def index(rows):
        return {(r["group"], r["account"], r["ticker"]): float(r["quantity"]) for r in rows}
    ia, ib = index(a), index(b)
    only_a = sorted(set(ia) - set(ib))
    only_b = sorted(set(ib) - set(ia))
    differ = sorted(k for k in set(ia) & set(ib) if abs(ia[k] - ib[k]) > tolerance)
    red = lambda k: {"group": k[0], "account": _mask(k[1]), "ticker": k[2]}  # noqa: E731
    return {
        "a_count": len(ia), "b_count": len(ib),
        "only_in_a": [red(k) for k in only_a],
        "only_in_b": [red(k) for k in only_b],
        "quantity_mismatch": [{**red(k), "a": ia[k], "b": ib[k]} for k in differ],
        "match": not (only_a or only_b or differ),
    }
