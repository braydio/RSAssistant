"""Evidence-based fractional-share policy classification (pure, no I/O).

Deliberately stricter than the legacy ``alert_processing.resolve_round_up_
confirmation``: *round to nearest whole* is NOT an unconditional round-up (a
0.1-share fraction rounds to zero), LLM labels are advisory and can never
override an explicit contrary filing clause, and nothing is auto-executable
without an effective date and unconditional round-up evidence from a primary
source. This module is not wired into autobuy.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

PARSER_VERSION = "split-policy-1"
PRIMARY_SOURCES = {"sec_filing", "issuer_release", "nasdaq"}


class Policy(str, Enum):
    ROUND_UP_UNCONDITIONAL = "round_up_unconditional"
    ROUND_TO_NEAREST = "round_to_nearest"
    CASH_IN_LIEU = "cash_in_lieu"
    AGGREGATED_PARTICIPANT = "aggregated_participant"
    ROUND_DOWN = "round_down"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


# Legacy / LLM labels -> canonical policy. "rounded_to_nearest_whole" is NOT
# mapped to ROUND_UP_UNCONDITIONAL.
_LABELS = {
    "rounded_up": Policy.ROUND_UP_UNCONDITIONAL,
    "round_up": Policy.ROUND_UP_UNCONDITIONAL,
    "round_up_unconditional": Policy.ROUND_UP_UNCONDITIONAL,
    "rounded_to_nearest_whole": Policy.ROUND_TO_NEAREST,
    "round_to_nearest": Policy.ROUND_TO_NEAREST,
    "cash_in_lieu": Policy.CASH_IN_LIEU,
    "aggregated_participant": Policy.AGGREGATED_PARTICIPANT,
    "rounded_down": Policy.ROUND_DOWN,
    "round_down": Policy.ROUND_DOWN,
    "no_fractional_shares": Policy.ROUND_DOWN,
}


def label_to_policy(label: str | None) -> Policy:
    return _LABELS.get(str(label or "").strip().lower().replace(" ", "_"), Policy.UNKNOWN)


@dataclass(frozen=True)
class Evidence:
    source_type: str  # sec_filing | issuer_release | nasdaq | discord_feed | llm
    policy_label: str
    scope: str = "unspecified"
    clause: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class Decision:
    policy: Policy
    auto_executable: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    contrary: tuple[Evidence, ...] = field(default_factory=tuple)


def fingerprint(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text or "").strip().lower().encode()).hexdigest()[:24]


def classify(evidence: Iterable[Evidence], *, effective_date: str | None) -> Decision:
    items = list(evidence)
    reasons: list[str] = []
    primary = [e for e in items if e.source_type in PRIMARY_SOURCES]
    advisory = [e for e in items if e.source_type not in PRIMARY_SOURCES]

    basis = primary or advisory
    policies = {label_to_policy(e.policy_label) for e in basis} - {Policy.UNKNOWN}
    if not policies:
        return Decision(Policy.UNKNOWN, False, ("no usable policy evidence",))
    if not primary:
        reasons.append("only advisory (feed/LLM) evidence; not eligible for auto-execution")

    if len(policies) > 1:
        return Decision(Policy.CONFLICT, False,
                        ("primary sources disagree: " + ", ".join(sorted(p.value for p in policies)),),
                        tuple(basis))

    policy = next(iter(policies))
    # An LLM/feed label never overrides an explicit contrary primary clause.
    contrary = tuple(e for e in advisory if label_to_policy(e.policy_label)
                     not in (policy, Policy.UNKNOWN)) if primary else ()
    if contrary:
        reasons.append("advisory evidence contradicts primary clause; primary retained")

    scopes = {e.scope for e in basis if label_to_policy(e.policy_label) == policy}
    if policy is Policy.ROUND_UP_UNCONDITIONAL and scopes <= {"unspecified", "beneficial_owner"} \
            and "registered_holder" not in scopes and "dtc_participant" not in scopes:
        reasons.append("scope not specific to the holder level; verify beneficial-owner treatment")

    executable = (
        policy is Policy.ROUND_UP_UNCONDITIONAL
        and bool(primary)
        and bool(effective_date)
        and not contrary
    )
    if policy is Policy.ROUND_UP_UNCONDITIONAL and not effective_date:
        reasons.append("missing effective date")
    if policy is Policy.ROUND_TO_NEAREST:
        reasons.append("nearest-whole is not an unconditional round-up")
    return Decision(policy, executable, tuple(reasons), contrary)


def corporate_action_key(issuer: str, ratio: str, effective_date: str | None) -> str:
    """Dedup key across feeds: issuer + ratio + effective date (not ticker alone)."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", str(s or "").lower())  # noqa: E731
    return f"{norm(issuer)}|{norm(ratio)}|{effective_date or 'unknown'}"
