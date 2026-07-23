"""Keep the configured auto-rsa checkout patched for holdings snapshots."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from utils.config_utils import (
    AUTO_RSA_DIR,
    AUTO_RSA_HOLDINGS_FILE,
    AUTO_RSA_PATCH_ENABLED,
    AUTO_RSA_PATCH_STATE_FILE,
)
from utils.logging_setup import logger


PATCH_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply-auto-rsa-patch.sh"


def _load_recorded_auto_rsa_dir() -> str:
    try:
        payload = json.loads(Path(AUTO_RSA_PATCH_STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return ""
    return str(payload.get("auto_rsa_dir", "")).strip() if isinstance(payload, dict) else ""


def resolve_auto_rsa_dir() -> str:
    """Return the configured checkout, falling back to the last patched path."""

    return AUTO_RSA_DIR or _load_recorded_auto_rsa_dir()


def ensure_auto_rsa_holdings_patch() -> bool:
    """Check the holdings patch and reapply it when an update removed it."""

    if not AUTO_RSA_PATCH_ENABLED:
        logger.info("Auto-rsa patch health check disabled.")
        return False

    auto_rsa_dir = resolve_auto_rsa_dir()
    if not auto_rsa_dir:
        logger.warning("Auto-rsa patch check skipped; AUTO_RSA_DIR and patch state are empty.")
        return False
    if not PATCH_SCRIPT.exists():
        logger.error("Auto-rsa patcher script is missing: %s", PATCH_SCRIPT)
        return False

    env = os.environ.copy()
    env["AUTO_RSA_HOLDINGS_FILE"] = os.getenv(
        "AUTO_RSA_HOLDINGS_FILE",
        str(AUTO_RSA_HOLDINGS_FILE),
    )
    env["AUTO_RSA_PATCH_STATE_FILE"] = str(AUTO_RSA_PATCH_STATE_FILE)
    try:
        result = subprocess.run(
            [str(PATCH_SCRIPT), auto_rsa_dir],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("Unable to run auto-rsa patch health check: %s", exc)
        return False
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        logger.error(
            "Auto-rsa patch health check failed for %s: %s",
            auto_rsa_dir,
            output or f"exit code {result.returncode}",
        )
        return False

    logger.info("Auto-rsa patch health check completed: %s", output)
    return True
