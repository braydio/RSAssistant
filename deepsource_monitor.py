"""DeepSource GitHub check monitor.

This module polls the GitHub API for the repository's latest commit and
tracks the DeepSource check run associated with that commit. The monitor
logs a message whenever the DeepSource status changes, allowing operators
to host it alongside RSAssistant for continuous quality monitoring.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

POLL_INTERVAL = int(os.environ.get("DEEPSOURCE_POLL_INTERVAL", "300"))
GITHUB_REPO = os.environ.get("GITHUB_REPO", "braydio/RSAssistant")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
DEEPSOURCE_APP_NAME = os.environ.get("DEEPSOURCE_APP_NAME", "DeepSource")
SUCCESS_CONCLUSIONS = {"success", "neutral", "skipped"}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckRunState:
    """Container describing a GitHub check run."""

    run_id: int
    status: str
    conclusion: Optional[str]
    html_url: Optional[str]

    @property
    def is_failure(self) -> bool:
        """bool: ``True`` when the check finished with a failing result."""

        return (
            self.status == "completed"
            and (self.conclusion or "").lower() not in SUCCESS_CONCLUSIONS
        )


@dataclass(frozen=True)
class MonitorSnapshot:
    """Snapshot of the DeepSource status for a commit."""

    commit_sha: str
    check_run: Optional[CheckRunState]


def _github_headers() -> Dict[str, str]:
    """Return HTTP headers for GitHub API requests."""

    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def fetch_default_branch() -> str:
    """Return the default branch for :data:`GITHUB_REPO`.

    Returns:
        str: Default branch name.

    Raises:
        requests.HTTPError: If GitHub returns an error response.
        ValueError: When the API response lacks the ``default_branch`` key.
    """

    url = f"https://api.github.com/repos/{GITHUB_REPO}"
    response = requests.get(url, headers=_github_headers(), timeout=10)
    response.raise_for_status()
    data = response.json()
    branch = data.get("default_branch")
    if not branch:
        raise ValueError("GitHub repository response missing default_branch")
    return branch


def fetch_latest_commit_sha(branch: str) -> str:
    """Return the SHA of the latest commit on ``branch``.

    Args:
        branch: Branch to inspect.

    Returns:
        str: SHA hash of the newest commit on ``branch``.

    Raises:
        requests.HTTPError: If GitHub returns an error response.
        ValueError: If the response does not contain a commit ``sha`` field.
    """

    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{branch}"
    response = requests.get(url, headers=_github_headers(), timeout=10)
    response.raise_for_status()
    data = response.json()
    sha = data.get("sha")
    if not sha:
        raise ValueError("GitHub commit response missing sha")
    return sha


def _parse_check_run(payload: Dict[str, Any]) -> CheckRunState:
    """Convert a GitHub check run payload to :class:`CheckRunState`.

    Args:
        payload: Raw JSON payload describing a check run.

    Returns:
        CheckRunState: Parsed check run metadata.

    Raises:
        KeyError: If the payload lacks an ``id`` field.
    """

    return CheckRunState(
        run_id=int(payload["id"]),
        status=payload.get("status", ""),
        conclusion=payload.get("conclusion"),
        html_url=payload.get("html_url"),
    )


def fetch_deepsource_check_run(commit_sha: str) -> Optional[CheckRunState]:
    """Return the DeepSource check run for ``commit_sha`` if present.

    Args:
        commit_sha: Commit hash to inspect.

    Returns:
        Optional[CheckRunState]: The parsed DeepSource check run or ``None``
        when no matching run is attached to the commit.

    Raises:
        requests.HTTPError: If GitHub returns an error response.
    """

    url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/commits/{commit_sha}/check-runs"
    )
    headers = _github_headers()
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    payload = response.json()
    for run in payload.get("check_runs", []):
        app = run.get("app", {})
        if app.get("name") == DEEPSOURCE_APP_NAME:
            return _parse_check_run(run)
    return None


def build_snapshot(commit_sha: str) -> MonitorSnapshot:
    """Return the DeepSource status snapshot for ``commit_sha``.

    Args:
        commit_sha: Target commit hash.

    Returns:
        MonitorSnapshot: Snapshot containing the commit hash and DeepSource
        check run (if present).
    """

    check_run = fetch_deepsource_check_run(commit_sha)
    return MonitorSnapshot(commit_sha=commit_sha, check_run=check_run)


def should_notify(previous: Optional[MonitorSnapshot], current: MonitorSnapshot) -> bool:
    """Return ``True`` when ``current`` represents a new or changed status.

    Args:
        previous: Prior snapshot or ``None`` if this is the first sample.
        current: Newly fetched snapshot.

    Returns:
        bool: ``True`` when a notification should be emitted.
    """

    if previous is None:
        return True
    if previous.commit_sha != current.commit_sha:
        return True
    prev_run = previous.check_run
    curr_run = current.check_run
    if prev_run is None or curr_run is None:
        return (prev_run is None) != (curr_run is None)
    return (
        prev_run.run_id != curr_run.run_id
        or prev_run.status != curr_run.status
        or (prev_run.conclusion or "").lower()
        != (curr_run.conclusion or "").lower()
    )


def format_status_message(snapshot: MonitorSnapshot) -> str:
    """Return a human-readable status message for ``snapshot``.

    Args:
        snapshot: Snapshot to describe.

    Returns:
        str: Rendered status message summarizing the DeepSource check.
    """

    short_sha = snapshot.commit_sha[:7]
    run = snapshot.check_run
    if run is None:
        return f"No DeepSource check run found for commit {short_sha}."

    status = (run.status or "unknown").lower()
    if status == "completed":
        conclusion = (run.conclusion or "unknown").lower()
        message = f"DeepSource check completed ({conclusion}) on commit {short_sha}"
    else:
        message = f"DeepSource check {status} on commit {short_sha}"
    if run.html_url:
        message += f" – {run.html_url}"
    return message


def log_snapshot(snapshot: MonitorSnapshot) -> None:
    """Log ``snapshot`` with an appropriate severity level.

    Args:
        snapshot: Snapshot describing the current DeepSource status.
    """

    run = snapshot.check_run
    message = format_status_message(snapshot)
    if run is None:
        logger.warning(message)
    elif run.is_failure:
        logger.error(message)
    else:
        logger.info(message)


def monitor_deepsource(poll_interval: int = POLL_INTERVAL) -> None:
    """Continuously monitor the DeepSource GitHub check run.

    Args:
        poll_interval: Number of seconds to wait between polls.
    """

    previous: Optional[MonitorSnapshot] = None
    while True:
        try:
            branch = fetch_default_branch()
            commit_sha = fetch_latest_commit_sha(branch)
            snapshot = build_snapshot(commit_sha)
            if should_notify(previous, snapshot):
                log_snapshot(snapshot)
            previous = snapshot
        except (requests.HTTPError, ValueError) as exc:
            logger.error("GitHub API error: %s", exc)
        except requests.RequestException as exc:
            logger.error("Network error contacting GitHub: %s", exc)
        time.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    monitor_deepsource()
