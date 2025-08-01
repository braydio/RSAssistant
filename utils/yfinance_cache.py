"""Simple price cache using OpenBB with optional on-disk persistence."""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, Tuple

from openbb import obb

from utils.config_utils import VOLUMES_DIR


logger = logging.getLogger(__name__)

_CACHE: Dict[str, Tuple[float, float]] = {}
_FILE_CACHE_LOADED = False

# cache stored under volumes/cache to survive bot restarts
CACHE_FILE = VOLUMES_DIR / "cache" / "price_cache.json"
TTL_SECONDS = 600  # 10 minutes


def _load_cache_from_file() -> None:
    """Populate in-memory cache from :data:`CACHE_FILE` if present."""

    global _FILE_CACHE_LOADED
    if _FILE_CACHE_LOADED or not CACHE_FILE.exists():
        _FILE_CACHE_LOADED = True
        return

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for ticker, (ts, price) in data.items():
            _CACHE[ticker] = (float(ts), float(price))
        logger.debug("Loaded price cache from %s", CACHE_FILE)
    except Exception as e:
        logger.warning("Failed to load price cache: %s", e)
    finally:
        _FILE_CACHE_LOADED = True


def _save_cache_to_file() -> None:
    """Persist the in-memory cache to :data:`CACHE_FILE`."""

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f)
    except Exception as e:
        logger.warning("Failed to save price cache: %s", e)


def get_price(ticker: str) -> float | None:
    """Return the latest closing price for ``ticker`` using OpenBB.

    The price is cached in-memory and persisted to :data:`CACHE_FILE`. Cached
    values older than :data:`TTL_SECONDS` are refreshed via ``openbb``.
    """

    ticker = ticker.upper().strip()
    _load_cache_from_file()
    now = time.time()
    if ticker in _CACHE:
        ts, price = _CACHE[ticker]
        if now - ts < TTL_SECONDS:
            return price
    try:
        result = obb.equity.price.quote(symbol=ticker)
        if result.results:
            price = result.results[0].close or result.results[0].last_price
            if price is not None:
                price = round(float(price), 2)
                _CACHE[ticker] = (now, price)
                _save_cache_to_file()
                return price
        logger.warning("No data returned for %s", ticker)
    except Exception as e:
        logger.error("Failed to fetch price for %s: %s", ticker, e)
    return None
