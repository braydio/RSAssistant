"""Tests for the Yahoo market data provider."""

from __future__ import annotations

import unittest
from unittest import mock

import requests

from utils.trading.market_data import YahooMarketDataProvider


class FakeResponse:
    """Lightweight response stub for Yahoo Finance requests."""

    def __init__(self, status_code: int, json_data=None, headers=None) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


class YahooMarketDataProviderTest(unittest.TestCase):
    @mock.patch("time.sleep")
    @mock.patch("utils.trading.market_data.requests.get")
    def test_fetch_candles_retries_on_rate_limit(self, get_mock, sleep_mock):
        rate_limited = FakeResponse(status_code=429, headers={"Retry-After": "2"})
        successful = FakeResponse(
            status_code=200,
            json_data={
                "chart": {
                    "result": [
                        {
                            "timestamp": [1, 2],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [1, 2],
                                        "high": [1, 2],
                                        "low": [1, 2],
                                        "close": [1.1, 2.2],
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
        )
        get_mock.side_effect = [rate_limited, successful]

        provider = YahooMarketDataProvider(max_retries=3, backoff_seconds=0.5)
        candles = provider.fetch_candles("TQQQ", interval="1h", range_="5d")

        self.assertEqual(2, len(candles))
        self.assertEqual(2, get_mock.call_count)
        sleep_mock.assert_called_with(2.0)

    @mock.patch("time.sleep")
    @mock.patch("utils.trading.market_data.requests.get")
    def test_rate_limit_exhausts_retries(self, get_mock, sleep_mock):
        get_mock.return_value = FakeResponse(status_code=429)

        provider = YahooMarketDataProvider(max_retries=2, backoff_seconds=0.1)
        with self.assertRaises(requests.HTTPError):
            provider.fetch_candles("TQQQ")

        self.assertEqual(2, get_mock.call_count)
        sleep_mock.assert_called()


if __name__ == "__main__":
    unittest.main()
