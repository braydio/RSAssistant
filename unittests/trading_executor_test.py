"""Unit tests for the TradeExecutor adapter."""

from utils.trading.executor import TradeExecutor


def test_sell_includes_broker_in_payload():
    executor = TradeExecutor()  # dry-run mode

    response = executor.sell("TQQQ", "all", broker="Fidelity")

    assert response.success is True
    assert response.payload == {"symbol": "TQQQ", "amount": "all", "broker": "Fidelity"}


def test_sell_without_broker_omits_field():
    executor = TradeExecutor()  # dry-run mode

    response = executor.sell("TQQQ", "all")

    assert response.success is True
    assert response.payload == {"symbol": "TQQQ", "amount": "all"}
