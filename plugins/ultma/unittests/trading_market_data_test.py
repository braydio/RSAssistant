"""Tests for the yfinance market data provider."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

STAGING_ROOT = Path(__file__).resolve().parents[3]
if str(STAGING_ROOT) not in sys.path:
    sys.path.insert(0, str(STAGING_ROOT))

from plugins.ultma.market_data import YFinanceMarketDataProvider


class YFinanceMarketDataProviderTest(unittest.TestCase):
    @mock.patch("time.sleep")
    @mock.patch("plugins.ultma.market_data.yf.download")
    def test_fetch_candles_retries_on_empty(self, download_mock, sleep_mock):
        empty = pd.DataFrame()
        data = pd.DataFrame(
            {
                "Open": [1.0, 2.0],
                "High": [1.2, 2.2],
                "Low": [0.9, 1.8],
                "Close": [1.1, 2.1],
            },
            index=pd.to_datetime(["2024-01-01 10:00", "2024-01-01 11:00"]),
        )
        download_mock.side_effect = [empty, data]

        provider = YFinanceMarketDataProvider(max_retries=3, backoff_seconds=0.5)
        candles = provider.fetch_candles("TQQQ", interval="1h", range_="5d")

        self.assertEqual(2, len(candles))
        self.assertEqual(2, download_mock.call_count)
        sleep_mock.assert_called()

    @mock.patch("time.sleep")
    @mock.patch("plugins.ultma.market_data.yf.download")
    def test_empty_data_exhausts_retries(self, download_mock, sleep_mock):
        download_mock.return_value = pd.DataFrame()

        provider = YFinanceMarketDataProvider(max_retries=2, backoff_seconds=0.1)
        with self.assertRaises(ValueError):
            provider.fetch_candles("TQQQ")

        self.assertEqual(2, download_mock.call_count)
        sleep_mock.assert_called()


if __name__ == "__main__":
    unittest.main()
