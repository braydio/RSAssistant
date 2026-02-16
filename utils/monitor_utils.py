"""Monitoring helpers for holdings detection and de-duplication.

This module tracks alert/sell actions to avoid repeated notifications within
the same day. It stores a small JSON file under ``config``.
"""

from __future__ import annotations

import errno
import atexit
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Set

from utils.config_utils import CONFIG_DIR

logger = logging.getLogger(__name__)

CACHE_PATH = (Path(CONFIG_DIR) / "overdollar_actions.json").resolve()
_CACHE_LOCK = threading.RLock()
_CACHE_DATA: Dict[str, Set[str]] | None = None
_CACHE_DIRTY = False
_LAST_SAVE_MONOTONIC = 0.0
_SAVE_DEBOUNCE_SECONDS = 1.0


def _fd_usage_hint() -> str:
    """Best-effort FD usage detail to aid Errno 24 troubleshooting."""
    fd_dir = Path("/proc/self/fd")
    try:
        return f"fd_count={len(list(fd_dir.iterdir()))}"
    except Exception:
        return "fd_count=unknown"


def _load_cache_from_disk() -> Dict[str, Set[str]]:
    try:
        if CACHE_PATH.exists():
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            # Ensure set types
            return {k: set(v) for k, v in data.items() if isinstance(v, list)}
    except Exception as e:
        if isinstance(e, OSError) and e.errno == errno.EMFILE:
            logger.error("Failed to load monitor cache: %s (%s)", e, _fd_usage_hint())
        else:
            logger.error(f"Failed to load monitor cache: {e}")
    return {}


def _save_cache_to_disk(cache: Dict[str, Set[str]]):
    try:
        serializable = {k: sorted(list(v)) for k, v in cache.items()}
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    except Exception as e:
        if isinstance(e, OSError) and e.errno == errno.EMFILE:
            logger.error("Failed to save monitor cache: %s (%s)", e, _fd_usage_hint())
        else:
            logger.error(f"Failed to save monitor cache: {e}")


def _ensure_cache_loaded() -> Dict[str, Set[str]]:
    global _CACHE_DATA
    with _CACHE_LOCK:
        if _CACHE_DATA is None:
            _CACHE_DATA = _load_cache_from_disk()
        return _CACHE_DATA


def _flush_cache_if_needed(force: bool = False) -> None:
    global _CACHE_DIRTY, _LAST_SAVE_MONOTONIC
    with _CACHE_LOCK:
        if not _CACHE_DIRTY or _CACHE_DATA is None:
            return
        now = time.monotonic()
        if not force and now - _LAST_SAVE_MONOTONIC < _SAVE_DEBOUNCE_SECONDS:
            return
        _save_cache_to_disk(_CACHE_DATA)
        _CACHE_DIRTY = False
        _LAST_SAVE_MONOTONIC = now


atexit.register(lambda: _flush_cache_if_needed(force=True))


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def make_holding_key(broker: str, account: str, ticker: str) -> str:
    return f"{broker}:{account}:{ticker.upper()}"


def has_acted_today(broker: str, account: str, ticker: str) -> bool:
    cache = _ensure_cache_loaded()
    today = _today_key()
    key = make_holding_key(broker, account, ticker)
    return key in cache.get(today, set())


def record_action_today(broker: str, account: str, ticker: str):
    try_record_action_today(broker, account, ticker)


def try_record_action_today(broker: str, account: str, ticker: str) -> bool:
    """Atomically check+record an action for today.

    Returns:
        True when the action was newly recorded.
        False when it was already present.
    """
    global _CACHE_DIRTY

    today = _today_key()
    key = make_holding_key(broker, account, ticker)
    cache = _ensure_cache_loaded()
    with _CACHE_LOCK:
        actions = cache.setdefault(today, set())
        if key in actions:
            return False
        actions.add(key)
        if len(cache) > 5:
            for stale_key in sorted(cache.keys())[:-2]:
                cache.pop(stale_key, None)
        _CACHE_DIRTY = True
    _flush_cache_if_needed()
    return True
