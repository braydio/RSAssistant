import json
from pathlib import Path

from utils import config_utils


def test_get_account_nickname_creates_mapping(tmp_path, monkeypatch):
    tmp_mapping = tmp_path / "account_mapping.json"
    monkeypatch.setattr(config_utils, "ACCOUNT_MAPPING", tmp_mapping)

    nickname = config_utils.get_account_nickname("TestBroker", "1", "1234")
    assert nickname == "TestBroker 1 1234"

    with open(tmp_mapping, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data == {"TestBroker": {"1": {"1234": "TestBroker 1 1234"}}}


def test_ignore_tickers_file_and_env_merge(tmp_path, monkeypatch):
    # Prepare temp ignore file
    ignore_file = tmp_path / "ignore_tickers.txt"
    ignore_file.write_text("""
    # comment line
    aapl
    msft  # Long-term position

    
    """.strip(), encoding="utf-8")

    # Point module to temp file and set env variable
    monkeypatch.setattr(config_utils, "IGNORE_TICKERS_FILE", ignore_file)
    monkeypatch.setenv("IGNORE_TICKERS", "goog, amzn,, ")

    merged = config_utils._compute_ignore_tickers()
    # Uppercased unique set from both sources
    assert merged == {"AAPL", "MSFT", "GOOG", "AMZN"}


def test_ignore_brokers_file_and_env_merge(tmp_path, monkeypatch):
    ignore_file = tmp_path / "ignore_brokers.txt"
    ignore_file.write_text("""
    Fidelity
    Schwab  # Workplace plan


    """.strip(), encoding="utf-8")

    monkeypatch.setattr(config_utils, "IGNORE_BROKERS_FILE", ignore_file)
    monkeypatch.setenv("IGNORE_BROKERS", "tasty, , robinhood ")

    merged = config_utils._compute_ignore_brokers()

    assert merged == {"FIDELITY", "SCHWAB", "TASTY", "ROBINHOOD"}


def test_persistence_defaults_true():
    assert config_utils.CSV_LOGGING_ENABLED
    assert config_utils.EXCEL_LOGGING_ENABLED
    assert config_utils.SQL_LOGGING_ENABLED


def test_persistence_env_override(monkeypatch):
    monkeypatch.setenv("CSV_LOGGING_ENABLED", "false")
    monkeypatch.setenv("EXCEL_LOGGING_ENABLED", "false")
    monkeypatch.setenv("SQL_LOGGING_ENABLED", "false")
    import importlib

    cu = importlib.reload(config_utils)
    assert not cu.CSV_LOGGING_ENABLED
    assert not cu.EXCEL_LOGGING_ENABLED
    assert not cu.SQL_LOGGING_ENABLED
    assert cu.load_config()["persistence"] == {
        "csv": False,
        "excel": False,
        "sql": False,
    }
