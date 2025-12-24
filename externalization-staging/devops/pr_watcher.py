"""GitHub PR watcher for RSAssistant.

This module runs the RSAssistant bot and silently polls the GitHub
repository for merged pull requests. When a new merge is detected, the
current bot process is terminated, the repository is updated via
``git pull``, and the bot is restarted. The polling interval and
repository can be configured through environment variables.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime
from typing import Optional

import requests

POLL_INTERVAL = int(os.environ.get("PR_WATCH_INTERVAL", "60"))
GITHUB_REPO = os.environ.get("GITHUB_REPO", "braydio/RSAssistant")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def fetch_latest_merge_time() -> Optional[datetime]:
    """Return the ``merged_at`` time of the most recently merged PR.

    The function queries the GitHub API for the most recently updated
    closed pull request and returns its ``merged_at`` timestamp if the
    PR was merged. ``None`` is returned when no merged pull requests are
    found or when the GitHub API cannot be reached.
    """

    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls?state=closed&per_page=1&sort=updated&direction=desc"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        prs = response.json()
    except requests.RequestException as exc:
        print(f"[watcher] Failed to fetch PRs: {exc}")
        return None

    if prs and prs[0].get("merged_at"):
        return datetime.fromisoformat(prs[0]["merged_at"].replace("Z", "+00:00"))
    return None


def should_restart(
    last_merge: Optional[datetime], latest_merge: Optional[datetime]
) -> bool:
    """Return ``True`` when a new merge has occurred since ``last_merge``."""

    return latest_merge is not None and (
        last_merge is None or latest_merge > last_merge
    )


def run_bot() -> subprocess.Popen:
    """Launch the RSAssistant bot process."""

    return subprocess.Popen(["python", "RSAssistant.py"])


def main() -> None:
    """Run the watcher and restart the bot on merged pull requests."""

    bot_proc = run_bot()
    last_merge = fetch_latest_merge_time()

    while True:
        time.sleep(POLL_INTERVAL)
        latest_merge = fetch_latest_merge_time()
        has_new_merge = should_restart(last_merge, latest_merge)
        bot_running = bot_proc.poll() is None

        if has_new_merge:
            if bot_running:
                bot_proc.terminate()
                bot_proc.wait()
            subprocess.run(["git", "pull"], check=True)
            bot_proc = run_bot()
        elif not bot_running:
            # Keep the bot running even if it exits on its own.
            bot_proc = run_bot()

        if latest_merge is not None:
            last_merge = latest_merge


if __name__ == "__main__":
    main()
