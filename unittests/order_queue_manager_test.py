"""Tests for order queue persistence helpers."""

import json
import os
import tempfile

from utils import order_queue_manager


def test_update_order_time_updates_existing_entry():
    temp_dir = tempfile.TemporaryDirectory()
    queue_path = os.path.join(temp_dir.name, "order_queue.json")
    original_queue_file = order_queue_manager.QUEUE_FILE
    try:
        order_queue_manager.QUEUE_FILE = queue_path
        with open(queue_path, "w") as handle:
            json.dump(
                {
                    "TEST_20250101_0930_buy": {
                        "action": "buy",
                        "ticker": "TEST",
                        "quantity": 1,
                        "broker": "all",
                        "time": "2025-01-01 09:30:00",
                    }
                },
                handle,
            )

        updated = order_queue_manager.update_order_time(
            "TEST_20250101_0930_buy", "2025-01-02 09:30:00"
        )
        assert updated is True

        with open(queue_path, "r") as handle:
            data = json.load(handle)
        assert data["TEST_20250101_0930_buy"]["time"] == "2025-01-02 09:30:00"
    finally:
        order_queue_manager.QUEUE_FILE = original_queue_file
        temp_dir.cleanup()
