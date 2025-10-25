"""Unit tests for watch list presentation helpers."""

import os
import tempfile
from datetime import datetime as real_datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from utils.watch_utils import WatchListManager, parse_bulk_watchlist_message


class DummyContext:
    """Minimal async context stub for Discord send operations."""

    def __init__(self):
        self.sent_messages = []

    async def send(self, content=None, embed=None):  # pragma: no cover - exercised indirectly
        self.sent_messages.append({"content": content, "embed": embed})


class WatchUtilsTest(IsolatedAsyncioTestCase):
    """Validate watch list display helpers for Discord commands."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        watch_path = os.path.join(self.temp_dir.name, "watch.json")
        sell_path = os.path.join(self.temp_dir.name, "sell.json")
        self.manager = WatchListManager(watch_path, sell_path)
        self.ctx = DummyContext()

    def tearDown(self):  # pragma: no cover - cleanup
        self.temp_dir.cleanup()

    async def test_list_watched_tickers_without_prices(self):
        """Default watchlist view should omit price lookups."""
        self.manager.watch_list = {
            "TEST": {"split_date": "01/02", "split_ratio": "1-10"}
        }

        with patch("utils.watch_utils.get_last_stock_price") as price_mock:
            await self.manager.list_watched_tickers(self.ctx, include_prices=False)

        price_mock.assert_not_called()
        self.assertEqual(len(self.ctx.sent_messages), 1)
        embed = self.ctx.sent_messages[0]["embed"]
        self.assertIsNotNone(embed)
        self.assertEqual(embed.fields[0].name, "TEST")
        self.assertIn("Split Date: 01/02", embed.fields[0].value)
        self.assertIn("Split Ratio: 1-10", embed.fields[0].value)

    async def test_list_watched_tickers_with_prices(self):
        """Optional price view should append formatted price data."""
        self.manager.watch_list = {
            "TEST": {"split_date": "01/02", "split_ratio": "N/A"}
        }

        with patch(
            "utils.watch_utils.get_last_stock_price", return_value=12.34
        ) as price_mock:
            await self.manager.list_watched_tickers(self.ctx, include_prices=True)

        price_mock.assert_called_once_with("TEST")
        embed = self.ctx.sent_messages[0]["embed"]
        self.assertEqual(embed.fields[0].name, "TEST — $12.34")
        self.assertIn("Split Ratio: N/A", embed.fields[0].value)

    async def test_send_watchlist_prices_uses_chunk_sender(self):
        """Plain price output should delegate to chunked sender."""
        self.manager.watch_list = {
            "TEST": {"split_date": "01/02", "split_ratio": "1-10"}
        }

        chunk_mock = AsyncMock()
        with patch(
            "utils.watch_utils.send_large_message_chunks", chunk_mock
        ), patch("utils.watch_utils.get_last_stock_price", return_value=8.9):
            await self.manager.send_watchlist_prices(self.ctx)

        chunk_mock.assert_awaited_once_with(self.ctx, "TEST: $8.90")
        self.assertEqual(self.ctx.sent_messages, [])

    def test_parse_bulk_watchlist_message_supports_month_day(self):
        """Bulk parser should accept ratio-first entries with month/day dates."""

        content = """\
IPW 1-30 (purchase by 10/24)
GURE 1-10 (purchase by 10/24)
YYAI 1-50 (purchase by 10/24)
ENVB 1-12 (purchase by 10/27)
ABP 1-30 (purchase by 10/31)
"""

        entries = parse_bulk_watchlist_message(content)

        self.assertEqual(
            entries,
            [
                ("IPW", "10/24", "1-30"),
                ("GURE", "10/24", "1-10"),
                ("YYAI", "10/24", "1-50"),
                ("ENVB", "10/27", "1-12"),
                ("ABP", "10/31", "1-30"),
            ],
        )

    def test_move_expired_to_sell_uses_exact_day_for_month_day_dates(self):
        """Tickers using month/day dates should move immediately after the day passes."""

        self.manager.watch_list = {
            "IPW": {"split_date": "10/24", "split_ratio": "1-30"}
        }

        with patch("utils.watch_utils.datetime", wraps=real_datetime) as datetime_mock:
            datetime_mock.now.return_value = real_datetime(2024, 10, 24)
            self.manager.move_expired_to_sell()

        self.assertIn("IPW", self.manager.watch_list)
        self.assertEqual(self.manager.sell_list, {})

        # Advance a single day past the split date; the ticker should move to the sell list.
        with patch("utils.watch_utils.datetime", wraps=real_datetime) as datetime_mock:
            datetime_mock.now.return_value = real_datetime(2024, 10, 25)
            self.manager.move_expired_to_sell()

        self.assertNotIn("IPW", self.manager.watch_list)
        self.assertIn("IPW", self.manager.sell_list)
