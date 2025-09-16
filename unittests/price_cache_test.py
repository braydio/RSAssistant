"""Tests for the persistent market data price cache."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import price_cache


def test_get_price_persists_and_loads(tmp_path, monkeypatch):
    """`get_price` should persist prices to disk and reload them."""

    cache_file = tmp_path / "prices.json"
    monkeypatch.setattr(price_cache, "CACHE_FILE", cache_file)
    monkeypatch.setattr(price_cache, "_CACHE", {})
    monkeypatch.setattr(price_cache, "_FILE_CACHE_LOADED", False)

    fake_time = 1000
    monkeypatch.setattr(
        price_cache,
        "time",
        SimpleNamespace(time=lambda: fake_time),
    )

    monkeypatch.setattr(price_cache, "_fetch_price_from_api", lambda ticker: 10.0)
    price = price_cache.get_price("ABC")
    assert price == 10.0
    assert cache_file.exists()

    # Clear in-memory cache to force reload from disk
    monkeypatch.setattr(price_cache, "_CACHE", {})
    monkeypatch.setattr(price_cache, "_FILE_CACHE_LOADED", False)
    monkeypatch.setattr(
        price_cache,
        "_fetch_price_from_api",
        lambda ticker: (_ for _ in ()).throw(AssertionError()),
    )

    price = price_cache.get_price("ABC")
    assert price == 10.0


def test_fetch_price_from_api_parses_fallback(monkeypatch):
    """The HTTP fetcher should parse fallback price fields when needed."""

    class DummyResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    captured = {}

    def dummy_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return DummyResponse(
            {
                "quoteResponse": {
                    "result": [
                        {
                            "regularMarketPrice": None,
                            "postMarketPrice": 7.891,
                        }
                    ]
                }
            }
        )

    dummy_session = SimpleNamespace(get=dummy_get)
    monkeypatch.setattr(price_cache, "_get_session", lambda: dummy_session)

    price = price_cache._fetch_price_from_api("XYZ")
    assert price == 7.89
    assert captured["params"] == {"symbols": "XYZ"}
