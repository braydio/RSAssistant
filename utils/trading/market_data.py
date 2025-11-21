"""Market data helpers for the ULT-MA trading subsystem."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class Candle:
    """Represents a single OHLC candle."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float


class YahooMarketDataProvider:
    """Minimal wrapper for Yahoo Finance chart endpoint.

    The provider is intentionally simple—it fetches OHLC data for a symbol and
    interval, retrying transient errors. Yahoo's API is public and does not
    require authentication, making it a sensible default for the strategy. In
    production deployments the provider can be swapped with TradingView
    webhooks or a premium data source.
    """

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def __init__(self, max_retries: int = 3, backoff_seconds: float = 1.0) -> None:
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _calculate_backoff(self, attempt: int, retry_after: Optional[str]) -> float:
        """Return the backoff delay for the given attempt.

        Args:
            attempt: Zero-based attempt counter.
            retry_after: Optional ``Retry-After`` header value from Yahoo.

        Returns:
            Number of seconds to sleep before retrying.
        """

        if retry_after:
            try:
                delay = float(retry_after)
                return max(delay, self.backoff_seconds)
            except (TypeError, ValueError):
                pass
        return self.backoff_seconds * max(1, attempt + 1)

    def fetch_candles(
        self,
        symbol: str,
        interval: str = "4h",
        range_: str = "1mo",
    ) -> List[Candle]:
        """Return OHLC candles for ``symbol``."""

        params = {"interval": interval, "range": range_}
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    self.BASE_URL.format(symbol=symbol), params=params, timeout=10
                )
                if response.status_code == 429:
                    delay = self._calculate_backoff(
                        attempt, response.headers.get("Retry-After")
                    )
                    logger.warning(
                        "Yahoo Finance rate limit hit (attempt %s/%s); sleeping %.2fs",
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    if attempt + 1 == self.max_retries:
                        response.raise_for_status()
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                payload = response.json()
                result = payload.get("chart", {}).get("result", [])
                if not result:
                    raise ValueError("Unexpected Yahoo Finance response")
                data = result[0]
                timestamps = data.get("timestamp", [])
                indicators = data.get("indicators", {}).get("quote", [])
                if not timestamps or not indicators:
                    raise ValueError("Incomplete Yahoo Finance response")
                quote = indicators[0]
                candles: List[Candle] = []
                for idx, ts in enumerate(timestamps):
                    try:
                        candles.append(
                            Candle(
                                timestamp=ts,
                                open=float(quote["open"][idx]),
                                high=float(quote["high"][idx]),
                                low=float(quote["low"][idx]),
                                close=float(quote["close"][idx]),
                            )
                        )
                    except (TypeError, ValueError):
                        continue
                return candles
            except requests.RequestException as exc:  # pragma: no cover - network
                if attempt + 1 >= self.max_retries:
                    logger.error("Yahoo Finance fetch failed: %s", exc)
                    raise
                delay = self.backoff_seconds * (attempt + 1)
                logger.warning(
                    "Yahoo Finance fetch failed (attempt %s/%s): %s; retrying in %.2fs",
                    attempt + 1,
                    self.max_retries,
                    exc,
                    delay,
                )
                time.sleep(delay)

    def fetch_last_price(self, symbol: str) -> Optional[float]:
        """Return the latest closing price for ``symbol``."""

        candles = self.fetch_candles(symbol, interval="1h", range_="5d")
        if not candles:
            return None
        return candles[-1].close


__all__ = ["YahooMarketDataProvider", "Candle"]
