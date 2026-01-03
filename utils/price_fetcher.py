"""Price fetching utilities backed by yfinance with aggressive caching."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, Iterable

import pandas as pd

from utils.config_utils import VOLUMES_DIR


logger = logging.getLogger(__name__)

CACHE_FILE = VOLUMES_DIR / "cache" / "yfinance_price_cache.json"
TTL_SECONDS = 600
FAILURE_BACKOFF_SECONDS = 600
MAX_TICKERS_PER_BATCH = 50

_CACHE: Dict[str, tuple[float, float]] = {}
_FAILED_ATTEMPTS: Dict[str, float] = {}
_FILE_CACHE_LOADED = False


def _normalize_ticker(ticker: str) -> str:
    return ticker.upper().strip()


def _load_cache_from_file() -> None:
    """Load cached prices from disk once per process."""

    global _FILE_CACHE_LOADED
    if _FILE_CACHE_LOADED or not CACHE_FILE.exists():
        _FILE_CACHE_LOADED = True
        return

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as cache_fp:
            data = json.load(cache_fp)
        for symbol, (ts, price) in data.items():
            _CACHE[symbol] = (float(ts), float(price))
        logger.debug("Loaded price cache from %s", CACHE_FILE)
    except Exception as exc:
        logger.warning("Failed to load price cache: %s", exc)
    finally:
        _FILE_CACHE_LOADED = True


def _save_cache_to_file() -> None:
    """Persist the cache to disk."""

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as cache_fp:
            json.dump(_CACHE, cache_fp)
    except Exception as exc:
        logger.warning("Failed to save price cache: %s", exc)


def _chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _extract_last_close(frame: pd.DataFrame) -> float | None:
    if frame.empty or "Close" not in frame:
        return None
    close_series = frame["Close"].dropna()
    if close_series.empty:
        return None
    return round(float(close_series.iloc[-1]), 2)


def _fetch_prices(tickers: list[str]) -> Dict[str, float]:
    """Fetch latest prices for tickers using yfinance."""

    if not tickers:
        return {}

    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance is not installed; cannot fetch prices.")
        return {}

    prices: Dict[str, float] = {}
    for batch in _chunked(tickers, MAX_TICKERS_PER_BATCH):
        try:
            data = yf.download(
                tickers=batch,
                period="1d",
                interval="1m",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        except Exception as exc:
            logger.warning("yfinance download failed for %s: %s", batch, exc)
            continue

        if data.empty:
            continue

        if isinstance(data.columns, pd.MultiIndex):
            for ticker in batch:
                if ticker not in data.columns.levels[0]:
                    continue
                price = _extract_last_close(data[ticker])
                if price is not None:
                    prices[ticker] = price
        else:
            price = _extract_last_close(data)
            if price is not None:
                prices[batch[0]] = price

    return prices


def get_last_prices(tickers: Iterable[str]) -> Dict[str, float | None]:
    """Return latest prices for tickers with caching and backoff."""

    symbols = [_normalize_ticker(ticker) for ticker in tickers]
    symbols = [symbol for symbol in symbols if symbol]
    if not symbols:
        return {}

    _load_cache_from_file()
    now = time.time()
    results: Dict[str, float | None] = {}
    to_fetch: list[str] = []

    for symbol in dict.fromkeys(symbols):
        cached = _CACHE.get(symbol)
        cached_ts = cached[0] if cached else 0.0
        cached_price = cached[1] if cached else None
        if cached and now - cached_ts < TTL_SECONDS:
            results[symbol] = cached_price
            continue

        failure_ts = _FAILED_ATTEMPTS.get(symbol)
        if failure_ts and now - failure_ts < FAILURE_BACKOFF_SECONDS:
            results[symbol] = cached_price
            continue

        to_fetch.append(symbol)
        results[symbol] = cached_price

    updated = False
    if to_fetch:
        fetched = _fetch_prices(to_fetch)
        for symbol in to_fetch:
            price = fetched.get(symbol)
            if price is not None:
                _CACHE[symbol] = (now, price)
                _FAILED_ATTEMPTS.pop(symbol, None)
                results[symbol] = price
                updated = True
            else:
                _FAILED_ATTEMPTS[symbol] = now

    if updated:
        _save_cache_to_file()

    return results


def get_last_stock_price(ticker: str) -> float | None:
    """Return the latest cached price for a single ticker."""

    prices = get_last_prices([ticker])
    return prices.get(_normalize_ticker(ticker))
