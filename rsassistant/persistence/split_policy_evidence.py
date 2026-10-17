"""Persist and read split-policy evidence (idempotent, append-only)."""

from __future__ import annotations

from os import PathLike
from typing import Any

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from rsassistant.services.split_policy_classifier import (
    PARSER_VERSION, Evidence, fingerprint)
from utils.config_utils import SQL_DATABASE


def _connect(database=None):
    conn = connect_runtime_db(database or SQL_DATABASE)
    run_migrations(conn)
    return conn


def record_evidence(ticker: str, split_date: str, evidence: Evidence, *,
                    database: str | PathLike[str] | None = None) -> bool:
    """Insert once per (event, source, fingerprint, label); True if newly stored."""
    fp = fingerprint((evidence.clause or "") + "|" + (evidence.source_url or ""))
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """INSERT OR IGNORE INTO split_policy_evidence
               (ticker, split_date, source_type, source_url, source_fingerprint,
                clause, scope, policy_label, parser_version)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (ticker.upper(), split_date, evidence.source_type, evidence.source_url, fp,
             (evidence.clause or "")[:2000], evidence.scope, evidence.policy_label,
             PARSER_VERSION),
        )
        return cur.rowcount == 1


def load_evidence(ticker: str, split_date: str, *,
                  database: str | PathLike[str] | None = None) -> list[Evidence]:
    with _connect(database) as conn:
        rows = conn.execute(
            "SELECT source_type, policy_label, scope, clause, source_url "
            "FROM split_policy_evidence WHERE ticker=? AND split_date=? ORDER BY evidence_id",
            (ticker.upper(), split_date)).fetchall()
    return [Evidence(*r) for r in rows]
