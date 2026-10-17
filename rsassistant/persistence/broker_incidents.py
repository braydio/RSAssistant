"""Broker incident registry: dedupe, shared-infrastructure grouping, recovery."""

from __future__ import annotations

from os import PathLike
from typing import Any

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from rsassistant.services.broker_health import Classification, Level, classify_error, scrub
from utils.config_utils import SQL_DATABASE

INFRA_PROFILE = "infrastructure"


def _connect(database: str | PathLike[str] | None = None):
    conn = connect_runtime_db(database or SQL_DATABASE)
    run_migrations(conn)
    return conn


def report_failure(
    profile: str,
    raw_error: object,
    *,
    database: str | PathLike[str] | None = None,
) -> dict[str, Any]:
    """Record one failure for ``profile`` (e.g. ``"fidelity:1"``).

    Infrastructure failures attach to a single shared incident regardless of
    how many profiles hit them; adapter/account failures are per profile. The
    stored detail is scrubbed. Returns ``{incident_id, created, level, ...}``.
    """
    cls: Classification = classify_error(raw_error)
    detail = scrub(raw_error)
    owner = INFRA_PROFILE if cls.level is Level.INFRASTRUCTURE else profile
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT incident_id FROM broker_incidents "
            "WHERE profile=? AND error_class=? AND root_cause=? AND status='open'",
            (owner, cls.error_class, cls.root_cause),
        ).fetchone()
        created = row is None
        if created:
            incident_id = conn.execute(
                """INSERT INTO broker_incidents
                   (level, profile, error_class, root_cause, severity)
                   VALUES (?,?,?,?,?)""",
                (cls.level.value, owner, cls.error_class, cls.root_cause, cls.severity),
            ).lastrowid
        else:
            incident_id = row[0]
            conn.execute(
                "UPDATE broker_incidents SET occurrences=occurrences+1, "
                "updated_at=CURRENT_TIMESTAMP WHERE incident_id=?",
                (incident_id,),
            )
        conn.execute(
            "INSERT INTO broker_incident_events(incident_id, kind, affected_profile, detail) "
            "VALUES (?, 'failure', ?, ?)",
            (incident_id, profile, detail),
        )
    return {
        "incident_id": incident_id, "created": created, "level": cls.level.value,
        "error_class": cls.error_class, "severity": cls.severity, "hint": cls.hint,
        "status": cls.status.value, "blocks_new_orders": cls.blocks_new_orders,
    }


def record_success(
    profile: str, *, database: str | PathLike[str] | None = None
) -> int:
    """Close this profile's open adapter/account incidents after a clean read-only
    success. Never closes shared infrastructure incidents or ambiguous-execution
    holds (those need an explicit operator/infra resolution)."""
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ids = [r[0] for r in conn.execute(
            "SELECT incident_id FROM broker_incidents WHERE profile=? AND status='open' "
            "AND level!='infrastructure' AND error_class!='ambiguous_execution'",
            (profile,),
        )]
        for i in ids:
            conn.execute(
                "UPDATE broker_incidents SET status='resolved', "
                "resolved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                "WHERE incident_id=?", (i,))
            conn.execute(
                "INSERT INTO broker_incident_events(incident_id, kind, affected_profile) "
                "VALUES (?, 'recovered', ?)", (i, profile))
    return len(ids)


def resolve_incident(
    incident_id: int, *, database: str | PathLike[str] | None = None
) -> bool:
    """Explicit operator/infra resolution (also releases an order hold)."""
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE broker_incidents SET status='resolved', resolved_at=CURRENT_TIMESTAMP, "
            "updated_at=CURRENT_TIMESTAMP WHERE incident_id=? AND status='open'",
            (incident_id,))
        if cur.rowcount:
            conn.execute(
                "INSERT INTO broker_incident_events(incident_id, kind) VALUES (?, 'resolved')",
                (incident_id,))
        return bool(cur.rowcount)


def is_profile_blocked(
    profile: str, *, database: str | PathLike[str] | None = None
) -> bool:
    """True while an unresolved ambiguous-execution hold exists for the profile."""
    with _connect(database) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM broker_incidents WHERE profile=? AND status='open' "
            "AND error_class='ambiguous_execution'", (profile,)).fetchone())


def open_incidents(
    *, database: str | PathLike[str] | None = None
) -> list[dict[str, Any]]:
    with _connect(database) as conn:
        rows = conn.execute(
            """SELECT i.incident_id, i.level, i.profile, i.error_class, i.severity,
                      i.occurrences, i.opened_at,
                      (SELECT count(DISTINCT affected_profile) FROM broker_incident_events e
                       WHERE e.incident_id=i.incident_id AND e.kind='failure')
               FROM broker_incidents i WHERE i.status='open'
               ORDER BY (i.severity='critical') DESC, i.incident_id"""
        ).fetchall()
    keys = ("incident_id", "level", "profile", "error_class", "severity",
            "occurrences", "opened_at", "affected_profiles")
    return [dict(zip(keys, r)) for r in rows]
