"""Monitoring helpers for holdings detection and de-duplication.

This module tracks alert/sell actions to avoid repeated notifications within
the same day. It stores a small JSON file under ``config``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Set

from utils.config_utils import CONFIG_DIR

logger = logging.getLogger(__name__)

CACHE_PATH = (Path(CONFIG_DIR) / "overdollar_actions.json").resolve()


def _load_cache() -> Dict[str, Set[str]]:
    try:
        if CACHE_PATH.exists():
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            # Ensure set types
            return {k: set(v) for k, v in data.items() if isinstance(v, list)}
    except Exception as e:
        logger.error(f"Failed to load monitor cache: {e}")
    return {}


def _save_cache(cache: Dict[str, Set[str]]):
    try:
        serializable = {k: sorted(list(v)) for k, v in cache.items()}
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to save monitor cache: {e}")


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def make_holding_key(broker: str, account: str, ticker: str) -> str:
    return f"{broker}:{account}:{ticker.upper()}"


def has_acted_today(broker: str, account: str, ticker: str) -> bool:
    cache = _load_cache()
    today = _today_key()
    key = make_holding_key(broker, account, ticker)
    return key in cache.get(today, set())


def record_action_today(broker: str, account: str, ticker: str):
    cache = _load_cache()
    today = _today_key()
    key = make_holding_key(broker, account, ticker)
    s = cache.setdefault(today, set())
    s.add(key)
    # Prune old days (keep only today and yesterday for tidiness)
    if len(cache) > 5:
        # sort keys, keep last 2
        for k in sorted(cache.keys())[:-2]:
            cache.pop(k, None)
    _save_cache(cache)
