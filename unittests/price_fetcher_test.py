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


def test_cache_bounded_and_evicts_oldest(monkeypatch):
    now = 4_000_000.0
    _setup_cache(monkeypatch, now)
    monkeypatch.setattr(price_fetcher, "MAX_CACHE_ENTRIES", 1000)
    monkeypatch.setattr(
        price_fetcher,
        "_fetch_prices",
        lambda syms: {s: 1.0 for s in syms},
    )
    symbols = [f"S{i:04d}" for i in range(1200)]
    for i, sym in enumerate(symbols):
        price_fetcher._CACHE[sym] = (now - 5000 + i, 1.0)
    price_fetcher.get_last_prices(["NEW"])
    assert len(price_fetcher._CACHE) == 1000
    assert "NEW" in price_fetcher._CACHE
    assert "S0000" not in price_fetcher._CACHE and "S1199" in price_fetcher._CACHE


def test_failed_attempts_expire_and_prior_value_returned(monkeypatch):
    now = 5_000_000.0
    _setup_cache(monkeypatch, now)
    price_fetcher._CACHE["ABC"] = (now - price_fetcher.TTL_SECONDS - 1, 7.0)
    price_fetcher._FAILED_ATTEMPTS["OLD"] = now - price_fetcher.FAILURE_BACKOFF_SECONDS - 1
    monkeypatch.setattr(price_fetcher, "_fetch_prices", lambda syms: {})
    assert price_fetcher.get_last_prices(["ABC"])["ABC"] == 7.0
    assert "OLD" not in price_fetcher._FAILED_ATTEMPTS
    assert "ABC" in price_fetcher._FAILED_ATTEMPTS


def test_very_old_entries_pruned(monkeypatch):
    now = 6_000_000_0.0
    _setup_cache(monkeypatch, now)
    price_fetcher._CACHE["ANCIENT"] = (now - price_fetcher.MAX_STALE_SECONDS - 1, 3.0)
    monkeypatch.setattr(price_fetcher, "_fetch_prices", lambda syms: {s: 2.0 for s in syms})
    price_fetcher.get_last_prices(["X"])
    assert "ANCIENT" not in price_fetcher._CACHE


def test_malformed_cache_file_rejected(monkeypatch, tmp_path):
    cache_file = tmp_path / "c.json"
    monkeypatch.setattr(price_fetcher, "CACHE_FILE", cache_file)
    monkeypatch.setattr(price_fetcher, "_CACHE", {})
    monkeypatch.setattr(price_fetcher, "_FILE_CACHE_LOADED", False)
    cache_file.write_text("[1,2,3]")
    price_fetcher._load_cache_from_file()
    assert price_fetcher._CACHE == {}

    now = price_fetcher.time.time()
    monkeypatch.setattr(price_fetcher, "_FILE_CACHE_LOADED", False)
    cache_file.write_text(
        '{"good":[%f,1.5],"nan":[1,NaN],"neg":[%f,-2],"bad":"x","abc":[1]}' % (now, now)
    )
    price_fetcher._load_cache_from_file()
    assert set(price_fetcher._CACHE) == {"GOOD"}


def test_save_is_atomic_and_compact(monkeypatch, tmp_path):
    cache_file = tmp_path / "sub" / "c.json"
    monkeypatch.setattr(price_fetcher, "CACHE_FILE", cache_file)
    monkeypatch.setattr(price_fetcher, "_CACHE", {"A": (1.0, 2.0)})
    price_fetcher._save_cache_to_file()
    assert cache_file.read_text() == '{"A":[1.0,2.0]}'
    assert [p.name for p in cache_file.parent.iterdir()] == ["c.json"]

    def boom(*_a, **_k):
        raise OSError("replace failed")

    monkeypatch.setattr(price_fetcher.os, "replace", boom)
    monkeypatch.setattr(price_fetcher, "_CACHE", {"B": (1.0, 9.0)})
    price_fetcher._save_cache_to_file()
    assert cache_file.read_text() == '{"A":[1.0,2.0]}'  # live file untouched
    assert [p.name for p in cache_file.parent.iterdir()] == ["c.json"]  # tmp cleaned


def test_concurrent_duplicate_fetch_coalesced(monkeypatch):
    import threading, time as _t

    now = _t.time()
    monkeypatch.setattr(price_fetcher, "_CACHE", {})
    monkeypatch.setattr(price_fetcher, "_FAILED_ATTEMPTS", {})
    monkeypatch.setattr(price_fetcher, "_FILE_CACHE_LOADED", True)
    monkeypatch.setattr(price_fetcher, "_save_cache_to_file", lambda: None)
    calls = []

    def slow_fetch(syms):
        calls.append(tuple(syms))
        _t.sleep(0.2)
        return {s: 5.0 for s in syms}

    monkeypatch.setattr(price_fetcher, "_fetch_prices", slow_fetch)
    out = []
    threads = [
        threading.Thread(target=lambda: out.append(price_fetcher.get_last_prices(["ZZZ"])))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert all(r["ZZZ"] == 5.0 for r in out)


def test_batches_of_fifty(monkeypatch):
    chunks = list(price_fetcher._chunked([str(i) for i in range(120)], price_fetcher.MAX_TICKERS_PER_BATCH))
    assert [len(c) for c in chunks] == [50, 50, 20]
