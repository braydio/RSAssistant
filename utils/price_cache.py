"""Persistent market data price cache backed by Nasdaq's quote endpoint."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Dict, Iterator, Tuple

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.config_utils import VOLUMES_DIR


logger = logging.getLogger(__name__)

CacheEntry = Tuple[float, float]
_CACHE: Dict[str, CacheEntry] = {}
_FAILED_ATTEMPTS: Dict[str, float] = {}
_FILE_CACHE_LOADED = False
_SESSION: Session | None = None

# cache stored under volumes/cache to survive bot restarts
CACHE_FILE = VOLUMES_DIR / "cache" / "nasdaq_price_cache.json"
TTL_SECONDS = 600  # 10 minutes
FAILURE_BACKOFF_SECONDS = 120  # Skip refetching a failing ticker for two minutes
API_URL_TEMPLATE = "https://api.nasdaq.com/api/quote/{symbol}/info"
API_DEFAULT_PARAMS = {"assetclass": "stocks"}
REQUEST_TIMEOUT = (3.05, 6)


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
            total=1,
            connect=1,
            read=1,
            status=1,
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
                "Referer": "https://www.nasdaq.com/",
                "Connection": "keep-alive",
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


def _symbol_candidates(ticker: str) -> Iterator[str]:
    """Yield Nasdaq API symbol representations for ``ticker``.

    The Nasdaq quote endpoint accepts a handful of symbol formats. The helper
    yields the normalized ticker plus common alternates (for example replacing
    dots with hyphens) to maximise the chance of a hit without requiring
    callers to understand the vendor specific nuances.
    """

    normalized = ticker.upper().strip()
    if not normalized:
        return

    yield normalized
    if "." in normalized:
        yield normalized.replace(".", "-")


def _parse_price_value(value: str | float | int | None) -> float | None:
    """Convert the Nasdaq price field to a float.

    The API often wraps prices in strings like ``"$123.45"`` or ``"N/A"``. The
    helper removes non-numeric characters while preserving the decimal point so
    the rest of the module can work with consistent ``float`` values.
    """

    if value in (None, "", "N/A", "n/a", "--"):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)

    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    cleaned = match.group(0)
    try:
        return round(float(cleaned), 2)
    except ValueError:
        logger.debug("Unable to parse price value %r", value)
        return None


def _extract_price(data: dict) -> float | None:
    """Return the best available price from a Nasdaq quote payload."""

    for section in ("primaryData", "extendedData"):
        block = data.get(section) or {}
        for field in ("lastSalePrice", "lastTradePrice", "lastPrice"):
            price = _parse_price_value(block.get(field))
            if price is not None:
                return price

    for field in ("lastSalePrice", "lastTradePrice", "lastPrice"):
        price = _parse_price_value(data.get(field))
        if price is not None:
            return price
    return None


def _fetch_price_from_api(ticker: str) -> float | None:
    """Fetch the most recent price for ``ticker`` using the Nasdaq quote API.

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
    for symbol in _symbol_candidates(ticker):
        url = API_URL_TEMPLATE.format(symbol=symbol)
        try:
            response = session.get(
                url, params=API_DEFAULT_PARAMS, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            logger.error("Request error while fetching %s (%s): %s", ticker, symbol, exc)
            continue

        if response.status_code in (403, 429):
            logger.warning(
                "Nasdaq quote API refused request for %s (status %s)",
                ticker,
                response.status_code,
            )
            continue

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("HTTP error while fetching %s (%s): %s", ticker, symbol, exc)
            continue

        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("Invalid JSON while fetching %s (%s): %s", ticker, symbol, exc)
            continue

        data = payload.get("data") or {}
        if not data:
            logger.debug("Nasdaq API returned no data for %s (%s)", ticker, symbol)
            continue

        price = _extract_price(data)
        if price is not None:
            return price
        logger.debug("Nasdaq API payload missing price for %s (%s)", ticker, symbol)

    logger.warning("Unable to retrieve price for %s from Nasdaq API", ticker)
    return None


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

    Notes
    -----
    When the Nasdaq API fails or times out the most recent cached value is
    returned even if it is older than :data:`TTL_SECONDS`. Subsequent refresh
    attempts are paused for :data:`FAILURE_BACKOFF_SECONDS` to avoid blocking
    the event loop with repeated network calls.
    """

    ticker = ticker.upper().strip()
    if not ticker:
        return None

    _load_cache_from_file()
    now = time.time()
    cache_entry = _CACHE.get(ticker)
    cached_ts = 0.0
    cached_price = None
    if cache_entry:
        cached_ts, cached_price = cache_entry
        if now - cached_ts < TTL_SECONDS:
            return cached_price

    failure_ts = _FAILED_ATTEMPTS.get(ticker)
    if failure_ts and now - failure_ts < FAILURE_BACKOFF_SECONDS:
        return cached_price

    price = _fetch_price_from_api(ticker)
    if price is not None:
        _CACHE[ticker] = (now, price)
        _FAILED_ATTEMPTS.pop(ticker, None)
        _save_cache_to_file()
        return price

    _FAILED_ATTEMPTS[ticker] = now
    return cached_price
