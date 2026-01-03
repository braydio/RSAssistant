"""Unit tests for watch list presentation helpers."""

import os
import tempfile
from datetime import datetime as real_datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import utils.watch_utils as watch_utils
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

        with patch("utils.watch_utils.get_last_prices") as price_mock:
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
            "utils.watch_utils.get_last_prices", return_value={"TEST": 12.34}
        ) as price_mock:
            await self.manager.list_watched_tickers(self.ctx, include_prices=True)
        price_mock.assert_called_once_with(self.manager.watch_list.keys())
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
        ), patch("utils.watch_utils.get_last_prices", return_value={"TEST": 8.9}):
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

    async def test_watch_command_accepts_bulk_format(self):
        """Bulk watch command should add every parsed ticker."""

        content = """\
YGMZ 1-16 (purchase by 11/11)
YDKG 1-100 (purchase by 11/13)
NCEW 1-8 (purchase by 11/13)
"""

        # Patch the global watch list manager used by the command helper
        with patch.object(watch_utils, "watch_list_manager", self.manager), patch(
            "utils.watch_utils.add_stock_to_excel_log", new_callable=AsyncMock
        ):
            await watch_utils.watch(self.ctx, text=content)

        self.assertEqual(
            self.manager.watch_list,
            {
                "YGMZ": {"split_date": "11/11", "split_ratio": "1-16"},
                "YDKG": {"split_date": "11/13", "split_ratio": "1-100"},
                "NCEW": {"split_date": "11/13", "split_ratio": "1-8"},
            },
        )

        # Three confirmations and one summary message should be sent.
        self.assertEqual(len(self.ctx.sent_messages), 4)
        self.assertEqual(
            self.ctx.sent_messages[-1]["content"], "Added 3 tickers to watchlist."
        )

    async def test_watch_command_validates_single_entry_inputs(self):
        """Single-line watch usage should enforce date and ratio validation."""

        with patch.object(watch_utils, "watch_list_manager", self.manager), patch(
            "utils.watch_utils.add_stock_to_excel_log", new_callable=AsyncMock
        ):
            await watch_utils.watch(self.ctx, text="TEST 11/11 1-5")

        self.assertIn("TEST", self.manager.watch_list)
        self.assertEqual(
            self.manager.watch_list["TEST"],
            {"split_date": "11/11", "split_ratio": "1-5"},
        )

        # Invalid date should surface an error message and abort
        self.ctx.sent_messages.clear()
        await watch_utils.watch(self.ctx, text="TESTX 2024-11-11 1-5")
        self.assertEqual(
            self.ctx.sent_messages[-1]["content"],
            "Invalid date format. Please use mm/dd, mm/dd/yy, or mm/dd/yyyy.",
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
