"""Unit tests for the TradeExecutor adapter."""

import sys
from pathlib import Path

STAGING_ROOT = Path(__file__).resolve().parents[3]
if str(STAGING_ROOT) not in sys.path:
    sys.path.insert(0, str(STAGING_ROOT))

from plugins.ultma.executor import TradeExecutor


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
