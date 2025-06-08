import logging
import time
from typing import Dict, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Tuple[float, float]] = {}
TTL_SECONDS = 600  # 10 minutes


def get_price(ticker: str) -> float | None:
    ticker = ticker.upper().strip()
    now = time.time()
    if ticker in _CACHE:
        ts, price = _CACHE[ticker]
        if now - ts < TTL_SECONDS:
            return price
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if not data.empty:
            price = round(float(data["Close"].iloc[-1]), 2)
            _CACHE[ticker] = (now, price)
            return price
        logger.warning("No data returned for %s", ticker)
    except Exception as e:
        logger.error("Failed to fetch price for %s: %s", ticker, e)
    return None
