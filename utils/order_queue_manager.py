# utils/order_queue_manager.py

"""Persistent order queue utilities."""

import json
import os
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


def update_order_time(order_id, new_time: str) -> bool:
    """Update the scheduled time for an existing queued order."""
    queue = _load_queue()
    if order_id not in queue:
        return False
    queue[order_id]["time"] = new_time
    _save_queue(queue)
    return True


def clear_order_queue():
    _save_queue({})


def list_order_queue():
    queue = _load_queue()
    return [
        f"{oid} → {data['action']} {data['quantity']} {data['ticker']} via {data['broker']} at {data['time']}"
        for oid, data in queue.items()
    ]


def list_order_queue_items():
    """Returns the queued orders as a list of (order_id, data) tuples."""
    queue = _load_queue()
    return list(queue.items())


def get_past_due_orders(reference_time) -> list[tuple[str, dict]]:
    """Return queued orders whose scheduled time is at or before reference_time."""
    queue = _load_queue()
    past_due = []
    for order_id, data in queue.items():
        try:
            execution_time = datetime.strptime(data["time"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if execution_time <= reference_time:
            past_due.append((order_id, data))
    return past_due
