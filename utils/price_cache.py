"""Persistent market data price cache backed by Yahoo's quote endpoint."""

from __future__ import annotations

import json
import logging
import time
from typing import Dict, Tuple

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.config_utils import VOLUMES_DIR


logger = logging.getLogger(__name__)

CacheEntry = Tuple[float, float]
_CACHE: Dict[str, CacheEntry] = {}
_FILE_CACHE_LOADED = False
_SESSION: Session | None = None

# cache stored under volumes/cache to survive bot restarts
CACHE_FILE = VOLUMES_DIR / "cache" / "yf_price_cache.json"
TTL_SECONDS = 600  # 10 minutes
API_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
REQUEST_TIMEOUT = 10


def _get_session() -> Session:
    """Return a shared HTTP session configured with retries.

    Returns
    -------
    requests.Session
        Session configured with retry/backoff settings for the quote API.
    """

    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=(408, 409, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            backoff_factor=0.5,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "User-Agent": "RSAssistant/1.0 (+https://github.com/braydio/RSAssistant)",
                "Accept": "application/json",
            }
        )
        _SESSION = session
    return _SESSION


def _load_cache_from_file() -> None:
    """Populate the in-memory cache from :data:`CACHE_FILE` if present."""

    global _FILE_CACHE_LOADED
    if _FILE_CACHE_LOADED or not CACHE_FILE.exists():
        _FILE_CACHE_LOADED = True
        return

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as cache_fp:
            data = json.load(cache_fp)
        for ticker, (ts, price) in data.items():
            _CACHE[ticker] = (float(ts), float(price))
        logger.debug("Loaded price cache from %s", CACHE_FILE)
    except Exception as exc:
        logger.warning("Failed to load price cache: %s", exc)
    finally:
        _FILE_CACHE_LOADED = True


def _save_cache_to_file() -> None:
    """Persist the in-memory cache to :data:`CACHE_FILE`."""

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as cache_fp:
            json.dump(_CACHE, cache_fp)
    except Exception as exc:
        logger.warning("Failed to save price cache: %s", exc)


def _extract_price(quote: dict) -> float | None:
    """Return the best available price from a Yahoo Finance quote payload.

    Parameters
    ----------
    quote : dict
        Parsed quote object from the Yahoo Finance quote endpoint.

    Returns
    -------
    float | None
        Rounded price when available, otherwise ``None``.
    """

    for field in ("regularMarketPrice", "postMarketPrice", "preMarketPrice"):
        value = quote.get(field)
        if value in (None, 0):
            continue
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            logger.debug("Invalid value %r for %s", value, field)
    return None


def _fetch_price_from_api(ticker: str) -> float | None:
    """Fetch the most recent price for ``ticker`` using the quote endpoint.

    Parameters
    ----------
    ticker : str
        Equity ticker symbol to fetch.

    Returns
    -------
    float | None
        Rounded market price when retrieval succeeds, otherwise ``None``.
    """

    session = _get_session()
    try:
        response = session.get(
            API_URL, params={"symbols": ticker}, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        logger.error("Request error while fetching %s: %s", ticker, exc)
        return None

    if response.status_code == 429:
        logger.warning("Quote API throttled request for %s", ticker)
        return None

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("HTTP error while fetching %s: %s", ticker, exc)
        return None

    try:
        payload = response.json()
    except ValueError as exc:
        logger.error("Invalid JSON while fetching %s: %s", ticker, exc)
        return None

    result = (payload.get("quoteResponse") or {}).get("result") or []
    if not result:
        logger.warning("Quote API returned no result for %s", ticker)
        return None

    price = _extract_price(result[0])
    if price is None:
        logger.warning("Quote API response missing usable price for %s", ticker)
    return price


def get_price(ticker: str) -> float | None:
    """Return the latest cached price for ``ticker`` with refresh as needed.

    Parameters
    ----------
    ticker : str
        Equity ticker symbol to look up.

    Returns
    -------
    float | None
        Cached or freshly fetched market price, or ``None`` when unavailable.
    """

    ticker = ticker.upper().strip()
    if not ticker:
        return None

    _load_cache_from_file()
    now = time.time()
    if ticker in _CACHE:
        ts, price = _CACHE[ticker]
        if now - ts < TTL_SECONDS:
            return price

    price = _fetch_price_from_api(ticker)
    if price is not None:
        _CACHE[ticker] = (now, price)
        _save_cache_to_file()
        return price

    return None
