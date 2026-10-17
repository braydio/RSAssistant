"""Bounded, side-effect-light recovery planning for broker incidents.

This module decides *what kind of* recovery is allowed; it never logs in, never
submits orders and never handles MFA codes. Callers execute the returned
``Action`` through the (future) typed broker worker.

Pieces:
* ``plan_recovery``     pure strategy per classified failure + attempt history
* ``SingleFlight``      one recovery at a time per login profile
* ``ChallengeStore``    short-lived single-use handles for a local protected UI
                        (the handle is an opaque id -- the OTP itself is never
                        stored or logged here)
* ``clean_stale_chromium_lock``  removes a Chromium profile lock only when the
                        owning process is proven dead on this host
* ``may_submit_orders`` circuit breaker backed by the incident registry
"""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from rsassistant.persistence import broker_incidents
from rsassistant.services.broker_health import Classification, Level


class Action(str, Enum):
    RESTART_BROWSER_ONCE = "restart_browser_once"
    CLEAN_STALE_LOCK = "clean_stale_lock"
    WAIT_RETRY_AFTER = "wait_retry_after"
    REQUEST_OPERATOR_CHALLENGE = "request_operator_challenge"
    REQUEST_REAUTH = "request_reauth"
    COOLDOWN = "cooldown"
    ESCALATE_CODE_REGRESSION = "escalate_code_regression"
    RECONCILE_BEFORE_ANYTHING = "reconcile_before_anything"
    NONE = "none"


@dataclass(frozen=True)
class Plan:
    action: Action
    delay_seconds: float = 0.0
    attempts_remaining: int = 0
    reason: str = ""


MAX_ATTEMPTS = {
    Action.RESTART_BROWSER_ONCE: 1,
    Action.WAIT_RETRY_AFTER: 3,
    Action.COOLDOWN: 3,
}
COOLDOWN_SECONDS = 15 * 60
DEFAULT_RATE_LIMIT_SECONDS = 60.0


def plan_recovery(
    c: Classification,
    attempts: dict[Action, int] | None = None,
    *,
    retry_after: float | None = None,
) -> Plan:
    """Choose the next bounded step. Never returns an order-related action."""
    attempts = attempts or {}

    def budget(action: Action) -> int:
        return MAX_ATTEMPTS.get(action, 1) - attempts.get(action, 0)

    if c.error_class == "ambiguous_execution":
        return Plan(Action.RECONCILE_BEFORE_ANYTHING, reason="never retry; reconcile with broker history")
    if c.level is Level.INFRASTRUCTURE:
        if budget(Action.RESTART_BROWSER_ONCE) > 0:
            return Plan(Action.RESTART_BROWSER_ONCE, attempts_remaining=budget(Action.RESTART_BROWSER_ONCE),
                        reason="one bounded browser restart")
        return Plan(Action.ESCALATE_CODE_REGRESSION, reason="infrastructure still failing after restart")
    if c.error_class == "challenge":
        return Plan(Action.REQUEST_OPERATOR_CHALLENGE, reason="needs operator approval/code")
    if c.error_class == "auth":
        return Plan(Action.REQUEST_REAUTH, reason="credentials or session need operator reauth")
    if c.error_class == "rate_limited":
        if budget(Action.WAIT_RETRY_AFTER) > 0:
            return Plan(Action.WAIT_RETRY_AFTER, delay_seconds=max(retry_after or DEFAULT_RATE_LIMIT_SECONDS, 1.0)
                        * (2 ** attempts.get(Action.WAIT_RETRY_AFTER, 0)),
                        attempts_remaining=budget(Action.WAIT_RETRY_AFTER), reason="honour Retry-After with backoff")
        return Plan(Action.COOLDOWN, delay_seconds=COOLDOWN_SECONDS, reason="rate-limit budget spent")
    if c.error_class in {"provider_unavailable", "timeout"}:
        if budget(Action.COOLDOWN) > 0:
            return Plan(Action.COOLDOWN, delay_seconds=COOLDOWN_SECONDS,
                        attempts_remaining=budget(Action.COOLDOWN), reason="provider outage cooldown")
        return Plan(Action.NONE, reason="cooldown budget spent; wait for operator")
    if c.error_class == "adapter_error":
        return Plan(Action.ESCALATE_CODE_REGRESSION, reason="likely adapter/page change; human-reviewed patch")
    return Plan(Action.NONE, reason="unclassified; capture trace")


class SingleFlight:
    """Allow at most one in-progress recovery per login profile."""

    def __init__(self) -> None:
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def try_acquire(self, profile: str) -> bool:
        with self._lock:
            if profile in self._active:
                return False
            self._active.add(profile)
            return True

    def release(self, profile: str) -> None:
        with self._lock:
            self._active.discard(profile)


class ChallengeStore:
    """Opaque single-use, expiring handles that deep-link to a local UI."""

    def __init__(self, ttl_seconds: float = 300.0, clock=time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._items: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def issue(self, profile: str) -> str:
        token = secrets.token_urlsafe(24)
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            self._items[digest] = (profile, self._clock() + self._ttl)
        return token

    def redeem(self, token: str) -> str | None:
        """Return the profile once; reused or expired handles return None."""
        digest = hashlib.sha256(str(token).encode()).hexdigest()
        with self._lock:
            item = self._items.pop(digest, None)
        if item is None or self._clock() > item[1]:
            return None
        return item[0]


def clean_stale_chromium_lock(profile_dir: Path | str, *, hostname: str | None = None) -> str:
    """Remove ``Singleton*`` locks only if provably owned by a dead local process.

    Returns one of ``removed``, ``no_lock``, ``active``, ``foreign_host``,
    ``unparseable``. ``foreign_host`` and ``active`` never delete anything.
    """
    profile = Path(profile_dir)
    lock = profile / "SingletonLock"
    if not lock.is_symlink():
        return "no_lock"
    host, _, pid_text = os.readlink(lock).rpartition("-")
    if not pid_text.isdigit() or not host:
        return "unparseable"
    if host != (hostname or socket.gethostname()):
        return "foreign_host"  # cannot prove another machine's process is dead
    try:
        os.kill(int(pid_text), 0)
        return "active"
    except ProcessLookupError:
        pass
    except PermissionError:
        return "active"
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        p = profile / name
        if p.is_symlink():
            p.unlink()
    return "removed"


def may_submit_orders(profile: str, *, database=None) -> bool:
    """Circuit breaker: False while an ambiguous-execution hold is open.

    Read-only monitoring, incident and reconciliation services keep running.
    """
    return not broker_incidents.is_profile_blocked(profile, database=database)
