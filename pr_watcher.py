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
from datetime import datetime, timezone
from typing import Optional

import requests

<<<<<<< Updated upstream
POLL_INTERVAL = 60
GITHUB_REPO = "braydio/RSAssistant"
GITHUB_TOKEN = "(Optional) Github Token Not Set"

# POLL_INTERVAL = int(os.environ.get("", "60"))
# GITHUB_REPO = os.environ.get("braydio/RSAssistant", "username/repository")
# GITHUB_TOKEN = os.environ.get("Github-Token Not-Set")
=======
POLL_INTERVAL = "60"
GITHUB_REPO = "braydio/RSAssistant"
GITHUB_TOKEN = "Optional Token Not Set"

# POLL_INTERVAL = int(os.environ.get("PR_WATCH_INTERVAL", "60"))
# GITHUB_REPO = os.environ.get("GITHUB_REPO", "your-org/RSAssistant")
# GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
>>>>>>> Stashed changes


def fetch_latest_merge_time() -> Optional[datetime]:
    """Return the ``merged_at`` time of the most recently merged PR.

    The function queries the GitHub API for the most recently updated
    closed pull request and returns its ``merged_at`` timestamp if the
    PR was merged. ``None`` is returned when no merged pull requests are
    found.
    """

    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls?state=closed&per_page=1&sort=updated&direction=desc"
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    prs = response.json()
    if prs and prs[0].get("merged_at"):
        return datetime.fromisoformat(prs[0]["merged_at"].replace("Z", "+00:00"))
    return None


def should_restart(
    last_merge: Optional[datetime], latest_merge: Optional[datetime]
) -> bool:
    """Return ``True`` when a new merge has occurred since ``last_merge``."""

    return (
        last_merge is not None
        and latest_merge is not None
        and latest_merge > last_merge
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
        if should_restart(last_merge, latest_merge):
            bot_proc.terminate()
            bot_proc.wait()
            subprocess.run(["git", "pull"], check=True)
            bot_proc = run_bot()
        if latest_merge is not None:
            last_merge = latest_merge


if __name__ == "__main__":
    main()
