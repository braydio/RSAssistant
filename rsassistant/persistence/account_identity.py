"""Canonical account identity: deterministic, non-destructive legacy mapping.

``Accounts`` rows are never modified or deleted. Rows that look like the same
account (same normalized broker + login group + last four) are *described* as
one canonical account. Last four alone is never treated as verification:
``verified`` stays 0 unless the legacy rows share the same full number, and a
cluster containing two different full numbers is flagged ``ambiguous`` and not
merged at all.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from os import PathLike
from typing import Any, Iterable

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import SQL_DATABASE

_NAMESPACE = uuid.UUID("5f0a1c7e-0b0d-4d2b-9a55-3a2c6a0b7d11")
FIXTURE_BROKERS = {"b", "brokera", "brokerb", "test", "fixture"}


def normalize_broker(value: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(value or "")).lower()


def normalize_group(value: str) -> str:
    """``"Fidelity 1"`` / ``"CHASE 1"`` / ``"1"`` -> ``"1"``."""
    text = str(value or "").strip()
    match = re.search(r"(\d+)\s*$", text)
    return match.group(1) if match else text.lower()


def account_forms(value: str) -> tuple[str, str | None]:
    """Return ``(last4, full_number_or_None)`` for any stored spelling.

    Masked values (``xxxx...7d15``) and 4-char values have no full number.
    """
    text = re.sub(r"[^0-9A-Za-z]", "", str(value or "")).lower()
    unmasked = text.lstrip("x") if re.match(r"^x+", text) else text
    if text.startswith("x"):
        return (unmasked[-4:].zfill(4) if unmasked.isdigit() else unmasked[-4:], None)
    last4 = text[-4:].zfill(4) if text.isdigit() else text[-4:]
    return last4, (text if len(text) > 4 else None)


@dataclass
class Plan:
    canonicals: dict[str, dict[str, Any]] = field(default_factory=dict)
    mappings: dict[int, dict[str, Any]] = field(default_factory=dict)


def _canonical_id(broker: str, group: str, last4: str, full: str | None) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{broker}|{group}|{last4}|{full or ''}"))


def build_plan(accounts: Iterable[dict[str, Any]]) -> Plan:
    """Pure function: legacy account rows -> canonical plan."""
    clusters: dict[tuple[str, str, str], list[tuple[dict, str | None]]] = {}
    for row in accounts:
        broker = normalize_broker(row["broker"])
        group = normalize_group(row.get("broker_number") or "")
        last4, full = account_forms(row["account_number"])
        clusters.setdefault((broker, group, last4), []).append((row, full))

    plan = Plan()
    for (broker, group, last4), members in clusters.items():
        fulls = {f for _, f in members if f}
        if len(fulls) > 1:
            # Contradictory evidence: do not merge anything in this cluster.
            for row, full in members:
                cid = _canonical_id(broker, group, last4, full or f"legacy:{row['account_id']}")
                plan.canonicals.setdefault(cid, dict(
                    broker_key=broker, group_key=group, last4=last4,
                    full_number_hash=_hash(full), ambiguous=True))
                plan.mappings[row["account_id"]] = dict(
                    canonical_account_id=cid, match_basis="ambiguous", verified=0)
            continue
        full = next(iter(fulls), None)
        cid = _canonical_id(broker, group, last4, full)
        plan.canonicals[cid] = dict(
            broker_key=broker, group_key=group, last4=last4,
            full_number_hash=_hash(full), ambiguous=False)
        spellings = {re.sub(r"[^0-9a-z]", "", str(r["account_number"]).lower())
                     for r, _ in members}
        for row, member_full in members:
            if full and all(f == full for _, f in members):
                basis, verified = "exact", 1  # every row carries the same full number
            elif len(spellings) == 1:
                basis, verified = "exact", 0  # identical text, but only last4 evidence
            else:
                basis, verified = "last4_compatible", 0
            plan.mappings[row["account_id"]] = dict(
                canonical_account_id=cid, match_basis=basis, verified=verified)
    return plan


def _hash(full: str | None) -> str | None:
    return hashlib.sha256(full.encode()).hexdigest()[:16] if full else None


def _connect(database: str | PathLike[str] | None = None):
    conn = connect_runtime_db(database or SQL_DATABASE)
    run_migrations(conn)
    return conn


def _legacy_rows(conn) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT account_id, broker, broker_number, account_number, account_nickname "
        "FROM Accounts"
    )
    return [dict(zip(("account_id", "broker", "broker_number", "account_number",
                      "account_nickname"), r)) for r in cur.fetchall()]


def _classify(conn, broker_key: str, legacy_ids: list[int], ambiguous: bool) -> str:
    if broker_key in FIXTURE_BROKERS:
        return "fixture"
    if ambiguous:
        return "ambiguous"
    marks = ",".join("?" * len(legacy_ids))
    if conn.execute(
        f"SELECT 1 FROM holdings_current WHERE account_id IN ({marks}) LIMIT 1",
        legacy_ids,
    ).fetchone():
        return "active"
    for table in ("OrderHistory", "HoldingsLive"):
        if conn.execute(
            f"SELECT 1 FROM {table} WHERE account_id IN ({marks}) LIMIT 1", legacy_ids
        ).fetchone():
            return "historical"
    return "dormant"


def refresh_canonical_map(*, database: str | PathLike[str] | None = None) -> dict[str, int]:
    """Idempotently (re)build canonical tables from ``Accounts``. Additive only."""
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = _legacy_rows(conn)
        plan = build_plan(rows)
        by_canon: dict[str, list[int]] = {}
        for legacy_id, m in plan.mappings.items():
            by_canon.setdefault(m["canonical_account_id"], []).append(legacy_id)
        for cid, c in plan.canonicals.items():
            status = _classify(conn, c["broker_key"], by_canon.get(cid, []), c["ambiguous"])
            conn.execute(
                """INSERT INTO canonical_accounts
                   (canonical_account_id, broker_key, group_key, last4, full_number_hash, status)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(canonical_account_id) DO UPDATE SET
                       status=excluded.status, updated_at=CURRENT_TIMESTAMP""",
                (cid, c["broker_key"], c["group_key"], c["last4"], c["full_number_hash"], status),
            )
        by_id = {r["account_id"]: r for r in rows}
        for legacy_id, m in plan.mappings.items():
            conn.execute(
                """INSERT INTO account_canonical_map
                   (legacy_account_id, canonical_account_id, match_basis, verified)
                   VALUES (?,?,?,?)
                   ON CONFLICT(legacy_account_id) DO UPDATE SET
                       canonical_account_id=excluded.canonical_account_id,
                       match_basis=excluded.match_basis, verified=excluded.verified
                   WHERE account_canonical_map.verified = 0""",
                (legacy_id, m["canonical_account_id"], m["match_basis"], m["verified"]),
            )
            row = by_id[legacy_id]
            for label, source in (
                (normalize_broker(row["broker"]) + " " + normalize_group(row.get("broker_number") or ""),
                 "accounts.broker"),
                (str(row.get("account_nickname") or "").strip().lower(), "accounts.nickname"),
            ):
                if label.strip():
                    conn.execute(
                        "INSERT OR IGNORE INTO account_aliases"
                        "(canonical_account_id, normalized_label, evidence_source) VALUES (?,?,?)",
                        (m["canonical_account_id"], label, source),
                    )
    return {"legacy_accounts": len(plan.mappings), "canonical_accounts": len(plan.canonicals)}


def mapping_report(*, database: str | PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Read-only counts per broker: canonical status and legacy-row fan-in."""
    with _connect(database) as conn:
        rows = conn.execute(
            """SELECT c.broker_key, c.status, count(DISTINCT c.canonical_account_id),
                      count(m.legacy_account_id),
                      sum(CASE WHEN m.verified=1 THEN 1 ELSE 0 END)
               FROM canonical_accounts c
               LEFT JOIN account_canonical_map m USING(canonical_account_id)
               GROUP BY c.broker_key, c.status ORDER BY c.broker_key, c.status"""
        ).fetchall()
    return [
        {"broker": b, "status": s, "canonical": n, "legacy_rows": l, "verified_rows": v or 0}
        for b, s, n, l, v in rows
    ]
