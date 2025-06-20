import json
from pathlib import Path

import pytest

from utils import order_queue_manager as oqm


def test_add_and_remove_order(tmp_path, monkeypatch):
    queue_file = tmp_path / "order_queue.json"
    monkeypatch.setattr(oqm, "QUEUE_FILE", queue_file)
    oqm.clear_order_queue()
    order_id = "ABC_20240101_0930_buy"
    data = {
        "action": "buy",
        "ticker": "ABC",
        "quantity": 1,
        "broker": "all",
        "time": "2024-01-01 09:30:00",
    }
    oqm.add_to_order_queue(order_id, data)
    queue = oqm.get_order_queue()
    assert order_id in queue
    oqm.remove_order(order_id)
    queue = oqm.get_order_queue()
    assert order_id not in queue
