"""Tests for sent !rsa order log persistence helpers."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from utils import order_send_log_manager


class OrderSendLogManagerTest(TestCase):
    """Validate sent-order log persistence and filtering."""

    def test_record_and_filter_sent_orders(self):
        """Recorded entries should be queryable by ticker and action."""

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_log = Path(temp_dir) / "order_send_log.json"
            with patch.object(order_send_log_manager, "ORDER_SEND_LOG_FILE", temp_log):
                order_send_log_manager.record_sent_rsa_order(
                    command="!rsa buy 2 TSLA all false",
                    channel_id=123,
                    ticker="TSLA",
                    action="buy",
                    quantity=2,
                    broker="all",
                    sent_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                )
                order_send_log_manager.record_sent_rsa_order(
                    command="!rsa sell 1 TSLA rh false",
                    channel_id=456,
                    ticker="TSLA",
                    action="sell",
                    quantity=1,
                    broker="rh",
                    sent_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
                )

                all_entries = order_send_log_manager.list_sent_rsa_orders(limit=10)
                self.assertEqual(len(all_entries), 2)
                self.assertEqual(all_entries[0]["action"], "sell")

                sell_entries = order_send_log_manager.list_sent_rsa_orders(
                    limit=10, ticker="tsla", action="sell"
                )
                self.assertEqual(len(sell_entries), 1)
                self.assertEqual(sell_entries[0]["broker"], "rh")

                latest = order_send_log_manager.latest_sent_rsa_order(ticker="TSLA")
                self.assertIsNotNone(latest)
                self.assertEqual(latest["action"], "sell")
