import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import parsing_utils


def test_public_incomplete_message(monkeypatch):
    """Public order messages without account info should create temporary orders."""
    monkeypatch.setattr(
        parsing_utils,
        "account_mapping",
        {"Public": {"4": {"0000": "Test"}}},
        raising=False,
    )
    parsing_utils.incomplete_orders.clear()
    parsing_utils.parse_order_message("Public 4: selling 0.10937 of VLCN")
    key = ("VLCN", "0000")
    assert key in parsing_utils.incomplete_orders
    order = parsing_utils.incomplete_orders[key]
    assert order["broker_name"] == "Public"
    assert order["broker_number"] == "4"
    assert order["action"] == "sell"
    assert pytest.approx(order["quantity"]) == 0.10937


<<<<<<< handle-missing-price-and-log-errors2025-06-25
def _setup_price_none(monkeypatch, call_tracker):
    """Helper to patch dependencies when price lookup returns None."""

    monkeypatch.setattr(parsing_utils, "get_last_stock_price", lambda s: None)

    def rec(msg, details):
        call_tracker["record"] = call_tracker.get("record", 0) + 1

    monkeypatch.setattr(parsing_utils, "record_error_message", rec)

    def csv_save(data):
        call_tracker["csv"] = call_tracker.get("csv", 0) + 1

    monkeypatch.setattr(parsing_utils, "save_order_to_csv", csv_save)
    monkeypatch.setattr(parsing_utils, "insert_order_history", lambda *a, **k: None)
    monkeypatch.setattr(parsing_utils, "update_excel_log", lambda *a, **k: None)


def test_handle_complete_order_price_none(monkeypatch):
    """handle_complete_order should log an error and skip saves when price is None."""

    calls = {}
    _setup_price_none(monkeypatch, calls)

    parsing_utils.parse_order_message("BBAE 1: buy 1 of ABC in xxxx1234: Success")

    assert calls.get("record", 0) == 1
    assert calls.get("csv") is None


def test_process_verified_orders_price_none(monkeypatch):
    """process_verified_orders should log an error and skip saves when price is None."""

    calls = {}
    _setup_price_none(monkeypatch, calls)

    order = {"action": "buy", "quantity": 1, "stock": "ABC"}
    parsing_utils.process_verified_orders("BBAE", "1", "1234", order)

    assert calls.get("record", 0) == 1
    assert calls.get("csv") is None
=======
def test_complete_order_price_fetch_failure(monkeypatch):
    """Orders should not be saved when price lookup fails."""

    calls = []
    monkeypatch.setattr(parsing_utils, "get_last_stock_price", lambda stock: None)
    monkeypatch.setattr(parsing_utils, "record_error_message", lambda *args: calls.append(args))
    saved = []
    monkeypatch.setattr(parsing_utils, "save_order_to_csv", lambda *a, **k: saved.append(True))

    parsing_utils.parse_order_message("Robinhood 1: buy 1 of ABC in xxxx1234: Success")

    assert calls, "record_error_message should be called"
    assert not saved, "order should not be saved to CSV"


def test_process_verified_orders_price_fetch_failure(monkeypatch):
    """Verified orders skip saving when price lookup fails."""

    calls = []
    monkeypatch.setattr(parsing_utils, "get_last_stock_price", lambda stock: None)
    monkeypatch.setattr(parsing_utils, "record_error_message", lambda *args: calls.append(args))
    saved = []
    monkeypatch.setattr(parsing_utils, "save_order_to_csv", lambda *a, **k: saved.append(True))

    parsing_utils.process_verified_orders(
        "Robinhood",
        "1",
        "1234",
        {"action": "buy", "quantity": 1, "stock": "ABC"},
    )

    assert calls, "record_error_message should be called"
    assert not saved, "order should not be saved to CSV"
>>>>>>> main
