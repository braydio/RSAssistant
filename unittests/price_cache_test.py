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
    monkeypatch.setattr(price_cache, "_FAILED_ATTEMPTS", {})
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

    captured = []

    def dummy_get(url, params=None, timeout=None):
        captured.append((url, params, timeout))
        return DummyResponse(
            {
                "data": {
                    "primaryData": {"lastSalePrice": "N/A"},
                    "extendedData": {"lastTradePrice": "$7.891"},
                }
            }
        )

    dummy_session = SimpleNamespace(get=dummy_get)
    monkeypatch.setattr(price_cache, "_get_session", lambda: dummy_session)

    price = price_cache._fetch_price_from_api("XYZ")
    assert price == 7.89
    assert captured[0][0] == price_cache.API_URL_TEMPLATE.format(symbol="XYZ")
    assert captured[0][1] == price_cache.API_DEFAULT_PARAMS
    assert captured[0][2] == price_cache.REQUEST_TIMEOUT


def test_fetch_price_from_api_retries_symbol_variants(monkeypatch):
    """Tickers with dots should try a hyphenated fallback for Nasdaq."""

    class DummyResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    responses = {
        price_cache.API_URL_TEMPLATE.format(symbol="BRK.B"): DummyResponse({"data": {}}),
        price_cache.API_URL_TEMPLATE.format(symbol="BRK-B"): DummyResponse(
            {
                "data": {
                    "primaryData": {"lastSalePrice": "$123.45"},
                }
            }
        ),
    }

    def dummy_get(url, params=None, timeout=None):
        return responses[url]

    dummy_session = SimpleNamespace(get=dummy_get)
    monkeypatch.setattr(price_cache, "_get_session", lambda: dummy_session)

    price = price_cache._fetch_price_from_api("BRK.B")
    assert price == 123.45


def test_get_price_returns_stale_on_failure(tmp_path, monkeypatch):
    """Stale cache entries should be returned when the API repeatedly fails."""

    cache_file = tmp_path / "prices.json"
    monkeypatch.setattr(price_cache, "CACHE_FILE", cache_file)
    monkeypatch.setattr(price_cache, "_CACHE", {})
    monkeypatch.setattr(price_cache, "_FAILED_ATTEMPTS", {})
    monkeypatch.setattr(price_cache, "_FILE_CACHE_LOADED", False)
    monkeypatch.setattr(price_cache, "_save_cache_to_file", lambda: None)

    stale_time = 10_000
    stale_price = 9.87
    monkeypatch.setattr(
        price_cache,
        "time",
        SimpleNamespace(time=lambda: stale_time),
    )
    price_cache._CACHE["ABC"] = (
        stale_time - price_cache.TTL_SECONDS - 5,
        stale_price,
    )
    monkeypatch.setattr(price_cache, "_fetch_price_from_api", lambda _: None)

    price = price_cache.get_price("ABC")
    assert price == stale_price
    assert price_cache._FAILED_ATTEMPTS["ABC"] == stale_time


def test_get_price_respects_failure_backoff(tmp_path, monkeypatch):
    """Recent failures should prevent another slow API call immediately."""

    cache_file = tmp_path / "prices.json"
    monkeypatch.setattr(price_cache, "CACHE_FILE", cache_file)
    monkeypatch.setattr(price_cache, "_CACHE", {})
    monkeypatch.setattr(price_cache, "_FAILED_ATTEMPTS", {})
    monkeypatch.setattr(price_cache, "_FILE_CACHE_LOADED", False)

    now = 5_000
    monkeypatch.setattr(
        price_cache,
        "time",
        SimpleNamespace(time=lambda: now),
    )
    cached_price = 4.56
    price_cache._CACHE["XYZ"] = (
        now - price_cache.TTL_SECONDS - 10,
        cached_price,
    )
    price_cache._FAILED_ATTEMPTS["XYZ"] = now - 10

    def should_not_run(_):
        raise AssertionError("API fetch attempted during backoff")

    monkeypatch.setattr(price_cache, "_fetch_price_from_api", should_not_run)

    price = price_cache.get_price("XYZ")
    assert price == cached_price
    assert price_cache._FAILED_ATTEMPTS["XYZ"] == now - 10
