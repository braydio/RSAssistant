"""Price fetching utilities backed by yfinance with aggressive caching."""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import Dict, Iterable

import pandas as pd

from utils.config_utils import PRICE_CACHE_MAX_ENTRIES, VOLUMES_DIR
from utils.performance_metrics import timed_call


logger = logging.getLogger(__name__)

CACHE_FILE = VOLUMES_DIR / "cache" / "yfinance_price_cache.json"
TTL_SECONDS = 600
FAILURE_BACKOFF_SECONDS = 600
MAX_TICKERS_PER_BATCH = 50
# Hard bounds for memory and the on-disk cache (oldest timestamps evicted first).
MAX_CACHE_ENTRIES = max(1, PRICE_CACHE_MAX_ENTRIES)
# Entries older than this are dropped; younger stale entries are still returned
# as a fallback when a refresh fails (legacy behavior, unchanged).
MAX_STALE_SECONDS = 30 * 24 * 3600
INFLIGHT_WAIT_SECONDS = 30.0

_CACHE: Dict[str, tuple[float, float]] = {}
_FAILED_ATTEMPTS: Dict[str, float] = {}
_FILE_CACHE_LOADED = False
_CACHE_LOCK = threading.Lock()
_INFLIGHT: Dict[str, threading.Event] = {}
_INFLIGHT_LOCK = threading.Lock()


def _normalize_ticker(ticker: str) -> str:
    return ticker.upper().strip()


def _valid_entry(symbol: object, ts: object, price: object) -> tuple[str, float, float] | None:
    """Return a normalized ``(symbol, ts, price)`` or ``None`` for bad data."""

    if not isinstance(symbol, str) or not symbol.strip() or len(symbol) > 16:
        return None
    try:
        ts_f, price_f = float(ts), float(price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(ts_f) and math.isfinite(price_f)) or ts_f <= 0 or price_f <= 0:
        return None
    return _normalize_ticker(symbol), ts_f, price_f


def _prune(now: float) -> None:
    """Bound ``_CACHE`` and ``_FAILED_ATTEMPTS``. Caller holds ``_CACHE_LOCK``."""

    for symbol in [s for s, (ts, _) in _CACHE.items() if now - ts > MAX_STALE_SECONDS]:
        del _CACHE[symbol]
    overflow = len(_CACHE) - MAX_CACHE_ENTRIES
    if overflow > 0:
        oldest = sorted(_CACHE, key=lambda sym: (_CACHE[sym][0], sym))[:overflow]
        for symbol in oldest:
            del _CACHE[symbol]
    for symbol in [
        s for s, ts in _FAILED_ATTEMPTS.items() if now - ts >= FAILURE_BACKOFF_SECONDS
    ]:
        del _FAILED_ATTEMPTS[symbol]


def _load_cache_from_file() -> None:
    """Load cached prices from disk once per process, rejecting bad entries."""

    global _FILE_CACHE_LOADED
    if _FILE_CACHE_LOADED or not CACHE_FILE.exists():
        _FILE_CACHE_LOADED = True
        return

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as cache_fp:
            data = json.load(cache_fp)
        if not isinstance(data, dict):
            raise ValueError("cache root is not an object")
        with _CACHE_LOCK:
            for count, (symbol, value) in enumerate(data.items()):
                if count >= MAX_CACHE_ENTRIES * 2:
                    break
                if not isinstance(value, (list, tuple)) or len(value) != 2:
                    continue
                entry = _valid_entry(symbol, value[0], value[1])
                if entry:
                    _CACHE[entry[0]] = (entry[1], entry[2])
            _prune(time.time())
        logger.debug("Loaded price cache from %s", CACHE_FILE)
    except Exception as exc:
        logger.warning("Failed to load price cache: %s", type(exc).__name__)
    finally:
        _FILE_CACHE_LOADED = True


def _save_cache_to_file() -> None:
    """Atomically persist a compact snapshot of the cache."""

    with _CACHE_LOCK:
        snapshot = dict(_CACHE)
    tmp_path = CACHE_FILE.with_name(CACHE_FILE.name + f".{os.getpid()}.tmp")
    try:
        if not CACHE_FILE.parent.exists():
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as cache_fp:
            json.dump(snapshot, cache_fp, separators=(",", ":"))
            cache_fp.flush()
            os.fsync(cache_fp.fileno())
        os.replace(tmp_path, CACHE_FILE)
    except Exception as exc:
        logger.warning("Failed to save price cache: %s", type(exc).__name__)
        try:
            tmp_path.unlink()
        except OSError:
            pass


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
            with timed_call("yfinance_batch"):
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

    with _CACHE_LOCK:
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

    # Single-flight: only one thread fetches a given symbol; others wait for it.
    owned: list[str] = []
    waiting: list[tuple[str, threading.Event]] = []
    with _INFLIGHT_LOCK:
        for symbol in to_fetch:
            event = _INFLIGHT.get(symbol)
            if event is None:
                _INFLIGHT[symbol] = threading.Event()
                owned.append(symbol)
            else:
                waiting.append((symbol, event))

    updated = False
    try:
        if owned:
            fetched = _fetch_prices(owned)
            with _CACHE_LOCK:
                for symbol in owned:
                    price = fetched.get(symbol)
                    if price is not None:
                        _CACHE[symbol] = (now, price)
                        _FAILED_ATTEMPTS.pop(symbol, None)
                        results[symbol] = price
                        updated = True
                    else:
                        _FAILED_ATTEMPTS[symbol] = now
                _prune(now)
    finally:
        with _INFLIGHT_LOCK:
            for symbol in owned:
                event = _INFLIGHT.pop(symbol, None)
                if event:
                    event.set()

    for symbol, event in waiting:
        event.wait(INFLIGHT_WAIT_SECONDS)
        with _CACHE_LOCK:
            cached = _CACHE.get(symbol)
        if cached:
            results[symbol] = cached[1]

    if updated:
        _save_cache_to_file()

    return results


def get_last_stock_price(ticker: str) -> float | None:
    """Return the latest cached price for a single ticker."""

    prices = get_last_prices([ticker])
    return prices.get(_normalize_ticker(ticker))
