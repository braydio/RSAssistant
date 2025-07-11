"""Tests for the persistent Yahoo Finance price cache."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import yfinance_cache


def test_get_price_persists_and_loads(tmp_path, monkeypatch):
    """`get_price` should persist prices to disk and reload them."""

    cache_file = tmp_path / "prices.json"
    monkeypatch.setattr(yfinance_cache, "CACHE_FILE", cache_file)
    monkeypatch.setattr(yfinance_cache, "_CACHE", {})
    monkeypatch.setattr(yfinance_cache, "_FILE_CACHE_LOADED", False)

    fake_time = 1000

    monkeypatch.setattr(
        yfinance_cache,
        "time",
        SimpleNamespace(time=lambda: fake_time),
    )

    class DummyTicker:
        def history(self, period="1d"):
            return pd.DataFrame({"Close": [10.0]})

    monkeypatch.setattr(yfinance_cache.yf, "Ticker", lambda t: DummyTicker())
    price = yfinance_cache.get_price("ABC")
    assert price == 10.0
    assert cache_file.exists()

    # Clear in-memory cache to force reload from disk
    monkeypatch.setattr(yfinance_cache, "_CACHE", {})
    monkeypatch.setattr(yfinance_cache, "_FILE_CACHE_LOADED", False)
    monkeypatch.setattr(yfinance_cache.yf, "Ticker", lambda t: (_ for _ in ()).throw(AssertionError()))

    price = yfinance_cache.get_price("ABC")
    assert price == 10.0
