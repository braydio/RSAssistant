import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import on_message_utils
from utils.watch_utils import watch_list_manager


def test_compute_account_missing_tickers(monkeypatch):
    monkeypatch.setattr(
        watch_list_manager,
        "get_watch_list",
        lambda: {"AAA": {}, "BBB": {}},
    )
    holdings = [
        {"broker": "Test", "account_name": "Nick1", "account": "1111", "ticker": "AAA"},
        {"broker": "Test", "account_name": "Nick1", "account": "1111", "ticker": "CCC"},
        {"broker": "Test", "account_name": "Nick2", "account": "2222", "ticker": "BBB"},
    ]
    result = on_message_utils.compute_account_missing_tickers(holdings)
    assert result == {
        "Test Nick1 (1111)": ["BBB"],
        "Test Nick2 (2222)": ["AAA"],
    }


def test_is_broker_ignored(monkeypatch):
    monkeypatch.setattr(
        on_message_utils,
        "IGNORE_BROKERS_SET",
        {"TASTYWORKS", "TD AMERITRADE"},
    )

    assert on_message_utils.is_broker_ignored("tastyworks") is True
    assert on_message_utils.is_broker_ignored("  td ameritrade  ") is True
    assert on_message_utils.is_broker_ignored("Fidelity") is False
    assert on_message_utils.is_broker_ignored("") is False
