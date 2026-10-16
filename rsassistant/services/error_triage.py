"""Pure helpers for the read-only Codex error-triage watcher.

Nothing here talks to Discord or spawns processes. The watcher cog uses these
to (1) fail closed on unsafe configuration, (2) build a fixed, read-only Codex
argv, (3) never forward raw Codex output, and (4) bound dedupe state.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable

WITHHELD = "[details withheld; inspect local logs]"
SEEN_MAX_ENTRIES = 1024
SEEN_TTL_SECONDS = 15 * 60
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}$")
_SAFE_FLAGS = {"--skip-git-repo-check"}
_MODEL_FLAGS = {"-m", "--model"}


def validate_codex_invocation(raw_command: str, cwd: Path) -> tuple[str, ...]:
    """Return the fixed Codex argv prefix or raise ``ValueError``.

    Accepted: ``codex exec`` (bare name resolved via PATH, or an absolute path
    whose basename is ``codex``) plus ``--skip-git-repo-check`` and
    ``--model/-m <name>``. Sandbox/approval/cd/output/json flags, wrappers and
    other executables are rejected; ``--sandbox read-only --ask-for-approval
    never`` is always appended and cannot be overridden.
    """
    try:
        tokens = shlex.split(raw_command or "")
    except ValueError as exc:
        raise ValueError("CODEX_EXEC_COMMAND is not parseable") from exc
    if len(tokens) < 2 or tokens[1] != "exec":
        raise ValueError("CODEX_EXEC_COMMAND must start with 'codex exec'")
    executable = tokens[0]
    if os.path.basename(executable) != "codex":
        raise ValueError("CODEX_EXEC_COMMAND executable must be codex")
    if os.path.isabs(executable):
        resolved = executable if os.access(executable, os.X_OK) and os.path.isfile(executable) else None
    elif os.sep in executable:
        resolved = None
    else:
        resolved = shutil.which(executable)
    if not resolved:
        raise ValueError("codex executable not found")
    if not Path(cwd).is_dir():
        raise ValueError("working directory is not a directory")

    extra: list[str] = []
    rest = tokens[2:]
    index = 0
    while index < len(rest):
        arg = rest[index]
        if arg in _SAFE_FLAGS:
            extra.append(arg)
        elif arg in _MODEL_FLAGS and index + 1 < len(rest) and _MODEL_RE.match(rest[index + 1]):
            extra.extend([arg, rest[index + 1]])
            index += 1
        else:
            raise ValueError("unsupported CODEX_EXEC_COMMAND option")
        index += 1
    return (
        resolved,
        "exec",
        *extra,
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
    )


def watcher_preflight(
    *,
    primary_channel: int,
    sender_ids,
    auto_rsa_dir: str,
    codex_command: str,
) -> list[str]:
    """Return names (never values) of configuration keys that block the watcher."""
    problems: list[str] = []
    if not primary_channel or primary_channel <= 0:
        problems.append("DISCORD_PRIMARY_CHANNEL")
    if not sender_ids:
        problems.append("AUTO_RSA_ERROR_WATCHER_SENDER_IDS")
    cwd = resolve_triage_cwd(auto_rsa_dir)
    if cwd is None:
        problems.append("AUTO_RSA_DIR")
    else:
        try:
            validate_codex_invocation(codex_command, cwd)
        except ValueError:
            problems.append("CODEX_EXEC_COMMAND")
    return problems


def resolve_triage_cwd(auto_rsa_dir: str) -> Path | None:
    """Return the explicit, readable ``AUTO_RSA_DIR`` or ``None`` (no fallback)."""
    if not auto_rsa_dir:
        return None
    candidate = Path(auto_rsa_dir).expanduser()
    if candidate.is_dir() and os.access(candidate, os.R_OK | os.X_OK):
        return candidate.resolve()
    return None


_REDACTIONS = (
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}"), "[redacted]"),
    (re.compile(r"\b(?:sk|pk|ghp|gho|xox[abprs]|AKIA)[A-Za-z0-9_\-]{12,}"), "[redacted]"),
    (re.compile(r"[MN][A-Za-z0-9_\-]{23,27}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,}"), "[redacted]"),
    (
        re.compile(
            r"(?i)\b([A-Za-z_]*(?:token|secret|password|passwd|api[_-]?key|authorization|cookie)[A-Za-z_]*)\s*[:=]\s*\S+"
        ),
        r"\1=[redacted]",
    ),
    (re.compile(r"(?i)\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[email]"),
    (re.compile(r"[A-Za-z0-9+_\-]{32,}={0,2}"), "[redacted]"),
    (re.compile(r"\b\d{6,}\b"), "[id]"),
    (re.compile(r"/home/[^/\s]+"), "~"),
    (re.compile(r"/Users/[^/\s]+"), "~"),
)
_MENTION_RE = re.compile(r"@(everyone|here)|<@[&!]?\d+>|<#\d+>", re.IGNORECASE)


def redact(text: str) -> str:
    """Best-effort scrub of secrets, identifiers, home paths and mentions."""
    cleaned = text or ""
    for pattern, replacement in _REDACTIONS:
        cleaned = pattern.sub(replacement, cleaned)
    return _MENTION_RE.sub("[mention]", cleaned)


_CATEGORIES = (
    ("permission", ("permissionerror", "permission denied", "forbidden", "unauthorized", "401", "403")),
    ("timeout/network", ("timeout", "timed out", "connection", "dns", "ssl", "unreachable")),
    ("database", ("sqlite", "database", "operationalerror", "locked", "integrityerror")),
    ("import/dependency", ("importerror", "modulenotfound", "no module named")),
    ("parsing/data", ("keyerror", "valueerror", "jsondecode", "parse", "typeerror", "indexerror")),
    ("broker/login", ("login", "2fa", "otp", "captcha", "selenium", "playwright")),
)
_PATH_LINE_RE = re.compile(r"([\w./\-]+\.py):(\d{1,6})")


def classify_error(text: str) -> str:
    lowered = (text or "").lower()
    for name, needles in _CATEGORIES:
        if any(needle in lowered for needle in needles):
            return name
    return "unclassified"


def verified_location(text: str, cwd: Path | None) -> str | None:
    """Return ``relative/path.py:line`` only if it exists inside ``cwd``."""
    if cwd is None:
        return None
    root = Path(cwd).resolve()
    for raw_path, line in _PATH_LINE_RE.findall(text or ""):
        candidate = Path(raw_path)
        candidate = candidate if candidate.is_absolute() else root / candidate
        try:
            resolved = candidate.resolve()
            relative = resolved.relative_to(root)
        except (ValueError, OSError):
            continue
        if resolved.is_file():
            return f"{relative}:{line}"
    return None


def summarize_triage_result(
    *, exit_code: int, stdout: str, stderr: str, runtime_context: dict
) -> str:
    """Return a bounded, plain-text status. Raw stdout/stderr is never echoed."""
    max_chars = max(200, int(runtime_context.get("max_chars", 1000)))
    combined = f"{stdout or ''}\n{stderr or ''}"
    category = classify_error(combined)
    location = verified_location(combined, runtime_context.get("cwd"))
    if exit_code == 0:
        status = "completed"
    elif exit_code == -1:
        status = "timed out"
    else:
        status = f"failed (exit {exit_code})"
    lines = [f"auto-rsa error watcher: read-only triage {status}."]
    if category == "unclassified" and not location:
        lines.append(WITHHELD)
    else:
        lines.append(f"Likely area: {category}.")
        if location:
            lines.append(f"Look at: {location}")
    lines.append(
        "Next: review local logs (volumes/logs/app.log) and the triggering alert. "
        "No files were changed."
    )
    message = "\n".join(lines)
    return redact(message)[:max_chars]


class BoundedSeen:
    """Capped, TTL-bound set of recently processed message IDs."""

    def __init__(
        self,
        max_entries: int = SEEN_MAX_ENTRIES,
        ttl_seconds: float = SEEN_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._entries: OrderedDict[int, float] = OrderedDict()
        self._max = max_entries
        self._ttl = ttl_seconds
        self._clock = clock

    def _evict(self) -> None:
        now = self._clock()
        while self._entries:
            oldest_id, observed = next(iter(self._entries.items()))
            if now - observed > self._ttl or len(self._entries) > self._max:
                self._entries.pop(oldest_id)
            else:
                break

    def seen(self, message_id: int) -> bool:
        self._evict()
        return message_id in self._entries

    def add(self, message_id: int) -> None:
        self._entries[message_id] = self._clock()
        self._entries.move_to_end(message_id)
        self._evict()

    def __len__(self) -> int:
        return len(self._entries)
