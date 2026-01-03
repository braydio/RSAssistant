"""Market data helpers for the ULT-MA trading subsystem."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    """Represents a single OHLC candle."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float


class YFinanceMarketDataProvider:
    """Minimal wrapper for yfinance candles.

    The provider is intentionally simple—it fetches OHLC data for a symbol and
    interval, retrying transient errors. Requests are spaced out with a basic
    backoff to reduce rate-limit risk. For production deployments the provider
    can be swapped with TradingView webhooks or a premium data source.
    """

    def __init__(self, max_retries: int = 3, backoff_seconds: float = 1.0) -> None:
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _calculate_backoff(self, attempt: int) -> float:
        return self.backoff_seconds * max(1, attempt + 1)

    def _normalize_interval(self, interval: str) -> Tuple[str, Optional[str]]:
        normalized = interval.lower().strip()
        if normalized == "4h":
            return "60m", "4H"
        return normalized, None

    def _resample_ohlc(self, data: pd.DataFrame, rule: str) -> pd.DataFrame:
        ohlc = data[["Open", "High", "Low", "Close"]].dropna(how="any")
        if ohlc.empty:
            return ohlc
        return (
            ohlc.resample(rule)
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
            .dropna(how="any")
        )

    def fetch_candles(
        self,
        symbol: str,
        interval: str = "4h",
        range_: str = "1mo",
    ) -> List[Candle]:
        """Return OHLC candles for ``symbol``."""
        interval, resample_rule = self._normalize_interval(interval)
        period = range_ or "1mo"

        for attempt in range(self.max_retries):
            try:
                data = yf.download(
                    tickers=symbol,
                    period=period,
                    interval=interval,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
            except Exception as exc:  # pragma: no cover - network
                if attempt + 1 >= self.max_retries:
                    logger.error("yfinance fetch failed: %s", exc)
                    raise
                delay = self._calculate_backoff(attempt)
                logger.warning(
                    "yfinance fetch failed (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            if data.empty:
                delay = self._calculate_backoff(attempt)
                logger.warning(
                    "yfinance returned no data (attempt %s/%s); retrying in %.2fs",
                    attempt + 1,
                    self.max_retries,
                    delay,
                )
                if attempt + 1 >= self.max_retries:
                    raise ValueError("yfinance returned no data")
                time.sleep(delay)
                continue

            if resample_rule:
                data = self._resample_ohlc(data, resample_rule)

            candles: List[Candle] = []
            for ts, row in data.iterrows():
                try:
                    candles.append(
                        Candle(
                            timestamp=int(ts.timestamp()),
                            open=float(row["Open"]),
                            high=float(row["High"]),
                            low=float(row["Low"]),
                            close=float(row["Close"]),
                        )
                    )
                except (TypeError, ValueError, KeyError):
                    continue
            return candles

        raise RuntimeError("Unable to fetch candles from yfinance")

    def fetch_last_price(self, symbol: str) -> Optional[float]:
        """Return the latest closing price for ``symbol``."""

        candles = self.fetch_candles(symbol, interval="1h", range_="5d")
        if not candles:
            return None
        return candles[-1].close


__all__ = ["YFinanceMarketDataProvider", "Candle"]
