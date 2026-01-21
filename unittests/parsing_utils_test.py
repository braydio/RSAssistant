"""Unit tests for :mod:`utils.parsing_utils`."""

import unittest
from unittest.mock import patch

from utils.parsing_utils import alert_channel_message


class AlertChannelMessageTest(unittest.TestCase):
    """Validate reverse split detection in alert messages."""

    def test_reverse_split_detects_reverse_split_phrase(self) -> None:
        message = "Super League Announces 1-for-12 Reverse Split (SLE)"
        result = alert_channel_message(message)

        self.assertEqual(result["ticker"], "SLE")
        self.assertTrue(result["reverse_split_confirmed"])

    def test_reverse_split_detects_reverse_stock_split_phrase(self) -> None:
        message = "Company announces reverse stock split (ABCD)"
        result = alert_channel_message(message)

        self.assertEqual(result["ticker"], "ABCD")
        self.assertTrue(result["reverse_split_confirmed"])

    def test_reverse_split_with_url_uses_remote_ticker(self) -> None:
        message = (
            "News | Super League Announces 1-for-12 Reverse Split\n\n"
            "https://www.globenewswire.com/news-release/2026/01/21/3222714/0/en/"
            "Super-League-Announces-1-for-12-Reverse-Split.html\n"
            "GlobeNewswire News Room\n"
            "Super League Announces 1-for-12 Reverse Split"
        )

        with patch("utils.parsing_utils._extract_ticker_from_remote_source", return_value="SLE"):
            result = alert_channel_message(message)

        self.assertEqual(result["ticker"], "SLE")
        self.assertTrue(result["reverse_split_confirmed"])


if __name__ == "__main__":
    unittest.main()
