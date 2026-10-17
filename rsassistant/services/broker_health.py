"""Typed broker-connection health and pure error classification.

Everything here is side-effect free: scrub text, classify a failure into one of
three levels (infrastructure / broker adapter / individual account), and derive
severity and an operator action hint. Persistence lives in
``rsassistant.persistence.broker_incidents``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Pattern


class Status(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    CHALLENGE_PENDING = "challenge_pending"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    ADAPTER_BROKEN = "adapter_broken"
    UNKNOWN = "unknown"
    DISABLED = "disabled"


class Level(str, Enum):
    INFRASTRUCTURE = "infrastructure"
    ADAPTER = "adapter"
    ACCOUNT = "account"


@dataclass(frozen=True)
class LoginProfileHealth:
    account_scope: str  # e.g. "fidelity:1" -- never a full account number
    status: Status = Status.UNKNOWN
    capabilities: tuple[str, ...] = ()
    checked_at: datetime | None = None
    last_success: datetime | None = None
    source_commit: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class Classification:
    level: Level
    error_class: str
    root_cause: str
    status: Status
    severity: str
    hint: str
    blocks_new_orders: bool = False


# Scrubbing -------------------------------------------------------------------

_SCRUBBERS: list[tuple[Pattern[str], str]] = [
    (re.compile(r"(?is)<(?:html|!doctype)[\s\S]*"), "[html removed]"),
    (re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret|password|passwd|cookie|"
                r"set-cookie|authorization|session(?:id)?|otp|code)\b\s*[:=]\s*\S+"),
     r"\1=[redacted]"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{8,}"), r"\1 [redacted]"),
    (re.compile(r"https?://\S+"), "[url]"),
    (re.compile(r"(?<!\d)\d{6}(?!\d)"), "[code]"),
    (re.compile(r"\b\d{5,}\b"), lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:]),
]


def scrub(text: object, limit: int = 300) -> str:
    """Remove secrets, URLs, HTML and long account numbers; truncate."""
    out = str(text or "")
    for pattern, repl in _SCRUBBERS:
        out = pattern.sub(repl, out)
    out = re.sub(r"\s+", " ", out).strip()
    return out[:limit]


# Classification --------------------------------------------------------------

# (regex, level, error_class, root_cause, status, severity, hint, blocks)
_RULES: list[tuple[str, Level, str, str, Status, str, str, bool]] = [
    (r"no usable sandbox|failed to connect to browser|chrome(?:driver)? not reachable|"
     r"session not created|cannot connect to chrome|devtoolsactiveport|driver not found|"
     r"executable.*(?:not found|doesn.t exist)",
     Level.INFRASTRUCTURE, "browser_launch", "browser_runtime", Status.PROVIDER_UNAVAILABLE,
     "critical", "Check docker_mode/--no-sandbox, Xvfb, Chromium/driver versions, /dev/shm.", False),
    (r"cannot open display|xvfb|\bDISPLAY\b.*(?:unset|not set)|no space left|/dev/shm",
     Level.INFRASTRUCTURE, "display_or_disk", "host_runtime", Status.PROVIDER_UNAVAILABLE,
     "critical", "Check Xvfb, disk space and /dev/shm in the container.", False),
    (r"name or service not known|temporary failure in name resolution|network is unreachable|"
     r"connection refused",
     Level.INFRASTRUCTURE, "network", "host_network", Status.PROVIDER_UNAVAILABLE,
     "warning", "Check container DNS/network.", False),
    (r"order button clicked but confirmation not detected|unknown order outcome|"
     r"ambiguous (?:order|execution)",
     Level.ACCOUNT, "ambiguous_execution", "unconfirmed_order", Status.DEGRADED,
     "critical", "Do NOT retry. Reconcile against the broker's order history first.", True),
    (r"device approval|approve (?:on|from) your|check phone app|verification (?:code|prompt)|"
     r"\b(?:sms|otp|2fa|mfa)\b|security (?:code|challenge)",
     Level.ACCOUNT, "challenge", "mfa_required", Status.CHALLENGE_PENDING,
     "warning", "Operator must approve the device / provide a fresh code.", False),
    (r"invalid (?:username|password|credentials)|incorrect password|login failed|"
     r"authentication failed|unauthori[sz]ed|\b401\b|session expired",
     Level.ACCOUNT, "auth", "credentials_or_session", Status.REAUTH_REQUIRED,
     "warning", "Reauthenticate this login profile.", False),
    (r"\b429\b|too many requests|rate.?limit",
     Level.ADAPTER, "rate_limited", "provider_rate_limit", Status.DEGRADED,
     "warning", "Back off; do not retry in a tight loop.", False),
    (r"\b50[0-4]\b|service unavailable|bad gateway|maintenance",
     Level.ADAPTER, "provider_unavailable", "provider_outage", Status.PROVIDER_UNAVAILABLE,
     "warning", "Provider outage; wait and re-check read-only.", False),
    (r"timed? ?out|timeout",
     Level.ADAPTER, "timeout", "provider_timeout", Status.DEGRADED,
     "warning", "Transient unless repeated; re-check read-only.", False),
    (r"no such element|element not found|selector|nonetype|keyerror|attributeerror|"
     r"unexpected (?:page|response)|json.?decode",
     Level.ADAPTER, "adapter_error", "adapter_mismatch", Status.ADAPTER_BROKEN,
     "critical", "Broker page/API changed or adapter bug; inspect with a captured trace.", False),
]
_COMPILED = [(re.compile(r[0], re.I), *r[1:]) for r in _RULES]


def classify_error(text: object) -> Classification:
    """Map a raw failure message to a three-level classification (pure)."""
    clean = str(text or "")
    for rx, level, cls, cause, status, severity, hint, blocks in _COMPILED:
        if rx.search(clean):
            return Classification(level, cls, cause, status, severity, hint, blocks)
    return Classification(
        Level.ADAPTER, "unclassified", "unknown", Status.UNKNOWN, "warning",
        "Unrecognised failure; capture the full trace.", False,
    )
