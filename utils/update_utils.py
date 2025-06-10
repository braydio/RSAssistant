import os
import subprocess
import sys
import logging

logger = logging.getLogger(__name__)


def _run(cmd):
    logger.info("Running: %s", ' '.join(cmd))
    return subprocess.run(cmd, check=True)


def pull_latest():
    """Fetch and pull latest changes from the current branch."""
    try:
        branch = (
            subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])\
            .decode().strip()
        )
        _run(["git", "fetch", "origin", branch])
        _run(["git", "pull", "--ff-only", "origin", branch])
        logger.info("Git pull successful")
        return True
    except Exception as e:
        logger.error("Git pull failed: %s", e)
        return False


def revert_last_pull():
    """Revert the last pull using reflog."""
    try:
        _run(["git", "reset", "--hard", "HEAD@{1}"])
        logger.info("Reverted last git pull")
        return True
    except Exception as e:
        logger.error("Revert failed: %s", e)
        return False


def restart_program():
    """Restart the current python program."""
    python = sys.executable
    os.execv(python, [python] + sys.argv)


def update_and_restart():
    if pull_latest():
        restart_program()


def revert_and_restart():
    if revert_last_pull():
        restart_program()
