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
