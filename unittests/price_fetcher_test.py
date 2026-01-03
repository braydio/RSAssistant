from utils import price_fetcher


def _setup_cache(monkeypatch, now):
    monkeypatch.setattr(price_fetcher, "_CACHE", {})
    monkeypatch.setattr(price_fetcher, "_FAILED_ATTEMPTS", {})
    monkeypatch.setattr(price_fetcher, "_FILE_CACHE_LOADED", True)
    monkeypatch.setattr(price_fetcher, "_load_cache_from_file", lambda: None)
    monkeypatch.setattr(price_fetcher, "_save_cache_to_file", lambda: None)
    monkeypatch.setattr(price_fetcher.time, "time", lambda: now)


def test_get_last_prices_uses_cache_when_fresh(monkeypatch):
    now = 1_000_000.0
    _setup_cache(monkeypatch, now)
    price_fetcher._CACHE["ABC"] = (now - 10, 10.0)

    monkeypatch.setattr(
        price_fetcher,
        "_fetch_prices",
        lambda *_args, **_kwargs: {"ABC": 99.0},
    )

    result = price_fetcher.get_last_prices(["ABC"])
    assert result["ABC"] == 10.0


def test_get_last_prices_fetches_when_stale(monkeypatch):
    now = 2_000_000.0
    _setup_cache(monkeypatch, now)
    price_fetcher._CACHE["ABC"] = (now - price_fetcher.TTL_SECONDS - 1, 10.0)

    monkeypatch.setattr(
        price_fetcher,
        "_fetch_prices",
        lambda *_args, **_kwargs: {"ABC": 12.5},
    )

    result = price_fetcher.get_last_prices(["ABC"])
    assert result["ABC"] == 12.5
    assert price_fetcher._CACHE["ABC"][1] == 12.5


def test_get_last_stock_price_returns_value(monkeypatch):
    now = 3_000_000.0
    _setup_cache(monkeypatch, now)

    monkeypatch.setattr(
        price_fetcher,
        "get_last_prices",
        lambda symbols: {"XYZ": 8.75},
    )

    assert price_fetcher.get_last_stock_price("XYZ") == 8.75
