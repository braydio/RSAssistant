import yfinance as yf
from yahoo_fin import stock_info as si
import subprocess
import asyncio
import requests
import time
import logging
from dotenv import load_dotenv
import os


# Global flag — users can disable ticker fallback here
# from utils.config_utils import ENABLE_TICKER_CLI
ENABLE_TICKER_CLI = False

logger = logging.getLogger(__name__)

# Simple cache
price_cache = {}


def price_from_ticker_cli(ticker: str) -> float:
    if not ENABLE_TICKER_CLI:
        logger.warning("Ticker-CLI pricing methohd disabled per pricing utils.")
        return 0.0
    try:
        result = subprocess.run(
            ["ticker", "--watchlist", ticker],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning(f"[ticker CLI] failed: {result.stderr.strip()}")
            return 0.0

        lines = result.stdout.splitlines()
        for line in lines:
            if line.strip().startswith(ticker):
                parts = line.strip().split("|")
                if len(parts) > 2:
                    price_str = parts[2].strip().replace(",", "")
                    return float(price_str)
    except FileNotFoundError:
        logger.warning("Ticker CLI not found.")
    except Exception as e:
        logger.error(f"[ticker CLI error] {e}")
    return 0.0


async def last_stock_price(ticker: str, retries: int = 1, delay: int = 2) -> float:
    ticker = ticker.upper()
    if ticker in price_cache:
        return price_cache[ticker]

    if ENABLE_TICKER_CLI:
        price = price_from_ticker_cli(ticker)
        if price:
            price_cache[ticker] = price
            return price
        logger.warning(
            "Ticker CLI fallback failed or not installed. Trying yfinance..."
        )

    for attempt in range(1, retries + 1):
        try:
            yf_ticker = yf.Ticker(ticker)
            hist = yf_ticker.history(period="1d")
            if not hist.empty and not hist["Close"].isna().all():
                price = float(hist["Close"].iloc[-1])
                price_cache[ticker] = price
                return price
        except Exception as e:
            logger.error(f"[yfinance][Attempt {attempt}] Failed to fetch {ticker}: {e}")
        await asyncio.sleep(delay * attempt)

    try:
        price = si.get_live_price(ticker)
        if price:
            price_cache[ticker] = float(price)
            return float(price)
    except Exception as e:
        logger.error(f"[yahoo_fin fallback] Failed for {ticker}: {e}")

    logger.error(f"Could not retrieve price for {ticker}, returning 0.0")
    return 0.0


logger = logging.getLogger(__name__)
price_cache = {}

# Load environment variables
load_dotenv()

# Get Alpaca API credentials from environment
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = "https://data.alpaca.markets/v2/stocks"


def get_last_stock_price(ticker: str) -> float:
    ticker = ticker.upper()
    if ticker in price_cache and time.time() - price_cache[ticker]["ts"] < 60:
        return price_cache[ticker]["price"]

    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
    }

    try:
        response = requests.get(
            f"{BASE_URL}/{ticker}/quotes/latest", headers=headers, timeout=5
        )
        response.raise_for_status()
        data = response.json()

        quote = data.get("quote", {})
        price = quote.get("ap") or quote.get("bp") or 0.0

        if price:
            price = float(price)
            price_cache[ticker] = {"price": price, "ts": time.time()}
            return price
        else:
            logger.warning(f"Alpaca API returned no price for {ticker}.")
    except Exception as e:
        logger.error(f"[Alpaca API] Error fetching {ticker}: {e}")

    return 0.0


# Example usage:
# print(get_stock_price_alpaca("AAPL"))
