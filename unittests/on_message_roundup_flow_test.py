"""Tests for the round-up processing flow in on_message."""

import os
import tempfile
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from utils.watch_utils import WatchListManager
from rsassistant.bot.handlers import on_message


class DummyChannel:
    """Minimal async channel stub for Discord send operations."""

    def __init__(self):
        self.send = AsyncMock()


class RoundUpFlowTest(IsolatedAsyncioTestCase):
    """Validate the unified round-up flow behavior."""

    async def test_process_round_up_flow_tracks_and_schedules(self):
        temp_dir = tempfile.TemporaryDirectory()
        watch_path = os.path.join(temp_dir.name, "watch.json")
        sell_path = os.path.join(temp_dir.name, "sell.json")
        manager = WatchListManager(watch_path, sell_path)
        channel = DummyChannel()

        split_watch_cache = {"watchlist": {}}

        def _get_status(ticker):
            return split_watch_cache["watchlist"].get(ticker.upper())

        def _add_split_watch(ticker, split_date):
            split_watch_cache["watchlist"][ticker.upper()] = {
                "split_date": split_date,
                "status": "buying",
                "accounts_bought": [],
                "accounts_sold": [],
            }

        try:
            with patch.object(on_message, "watch_list_manager", manager), patch.object(
                on_message, "attempt_autobuy", new=AsyncMock()
            ) as autobuy_mock, patch.object(
                on_message.split_watch_utils, "load_data", return_value=None
            ), patch.object(
                on_message.split_watch_utils, "get_status", side_effect=_get_status
            ), patch.object(
                on_message.split_watch_utils,
                "add_split_watch",
                side_effect=_add_split_watch,
            ):
                await on_message._process_round_up_flow(
                    bot=None,
                    channel=channel,
                    ticker="TEST",
                    split_date="2025-01-10",
                    split_ratio="1-10",
                    watch_date="1/10",
                )

            self.assertIn("TEST", manager.watch_list)
            self.assertIn("TEST", split_watch_cache["watchlist"])
            autobuy_mock.assert_awaited_once()
            self.assertGreaterEqual(channel.send.call_count, 1)
        finally:
            temp_dir.cleanup()
