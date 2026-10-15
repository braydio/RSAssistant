import asyncio
import time

from utils import utility_utils

MAPPING = {
    "Fidelity": {"1": {"1111": "a", "2222": "b"}},
    "Schwab": {"1": {"9999": "z"}},
}


def _row(broker, acct, ticker, qty, ts="2026-10-01 10:00:00"):
    return {
        "broker": broker, "broker_number": "1", "account_number": acct,
        "ticker": ticker, "quantity": qty, "price": 2.0, "position_value": 2 * qty,
        "account_total": 10.0, "observed_at": ts,
    }


class _Ctx:
    async def send(self, *a, **k):
        pass


def _patch(monkeypatch, rows, calls=None):
    def fake():
        if calls is not None:
            calls.append(1)
        return rows

    monkeypatch.setattr(utility_utils, "get_current_holdings", fake)
    monkeypatch.setattr(utility_utils, "load_account_mappings", lambda: MAPPING)


def test_single_snapshot_read_for_many_tickers(monkeypatch):
    calls = []
    _patch(monkeypatch, [_row("Fidelity", "1111", "AAA", 3)], calls)
    tickers = [f"T{i}" for i in range(100)] + ["AAA"]
    out = utility_utils.build_ticker_summaries(tickers)
    assert len(calls) == 1
    assert out["AAA"][0]["Fidelity"][1:] == (1, 2)
    assert out["T5"][0]["Fidelity"][1:] == (0, 2)


def test_empty_and_single(monkeypatch):
    _patch(monkeypatch, [])
    assert utility_utils.build_ticker_summaries([]) == {}
    statuses, ts = utility_utils.build_ticker_summaries(["AAA"])["AAA"]
    assert ts == "" and statuses["Fidelity"][1:] == (0, 2)


def test_batch_matches_single_ticker_path(monkeypatch):
    rows = [
        _row("Fidelity", "1111", "AAA", 3),
        _row("Fidelity", "2222", "AAA", 0),
        _row("Schwab", "9999", "BBB", 1, "2026-10-02 09:00:00"),
        _row("Fidelity", "1111", "AAA", 0, "2026-10-03 09:00:00"),  # newer: no longer held
        _row("Unknown", "5", "AAA", 2),
    ]
    _patch(monkeypatch, rows)
    batch = utility_utils.build_ticker_summaries(["AAA", "BBB"])
    for ticker in ("AAA", "BBB"):
        single = asyncio.run(utility_utils.track_ticker_summary(_Ctx(), ticker, collect=True))
        assert batch[ticker] == single
    assert batch["AAA"][1] == "2026-10-03 09:00:00"
    assert batch["AAA"][0]["Fidelity"][1] == 0


def test_100_tickers_scale_without_per_ticker_reads(monkeypatch):
    rows = [_row("Fidelity", "1111", f"T{i}", 1) for i in range(100)]
    calls = []
    _patch(monkeypatch, rows, calls)
    start = time.perf_counter()
    out = utility_utils.build_ticker_summaries([f"T{i}" for i in range(100)])
    assert len(calls) == 1 and len(out) == 100
    assert time.perf_counter() - start < 2.0
