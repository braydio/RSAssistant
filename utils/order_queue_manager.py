# utils/order_queue_manager.py

"""Persistent order queue utilities."""

import json
import os
from pathlib import Path
from datetime import datetime

from utils.config_utils import VOLUMES_DIR

QUEUE_FILE = VOLUMES_DIR / "db" / "order_queue.json"
QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_queue():
    if not os.path.exists(QUEUE_FILE):
        return {}
    with open(QUEUE_FILE, "r") as f:
        return json.load(f)


def _save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f, indent=2)


def add_to_order_queue(order_id, order_data):
    """
    Adds a new scheduled order.
    order_id can be a string like "XYZ_20250424_1245"
    order_data is a dict like {
        "action": "buy",
        "ticker": "XYZ",
        "quantity": 100,
        "broker": "rh",
        "time": "2025-04-24 12:45"
    }
    """
    queue = _load_queue()
    queue[order_id] = order_data
    _save_queue(queue)


def get_order_queue():
    """Returns the full order queue as a dict."""
    return _load_queue()


def remove_order(order_id):
    queue = _load_queue()
    if order_id in queue:
        del queue[order_id]
        _save_queue(queue)
        return True
    return False


def clear_order_queue():
    _save_queue({})


def list_order_queue():
    queue = _load_queue()
    return [
        f"{oid} → {data['action']} {data['quantity']} {data['ticker']} via {data['broker']} at {data['time']}"
        for oid, data in queue.items()
    ]
