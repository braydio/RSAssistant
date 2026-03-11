"""Unit tests for :mod:`utils.parsing_utils`."""

import unittest
from unittest.mock import patch

from utils.parsing_utils import alert_channel_message, parse_order_message


class AlertChannelMessageTest(unittest.TestCase):
    """Validate reverse split detection in alert messages."""

    def test_reverse_split_detects_reverse_split_phrase(self) -> None:
        message = "Super League Announces 1-for-12 Reverse Split (SLE)"
        result = alert_channel_message(message)

        self.assertEqual(result["ticker"], "SLE")
        self.assertTrue(result["reverse_split_confirmed"])

    def test_reverse_split_detects_share_consolidation_phrase(self) -> None:
        message = "PTLE Announces 1-for-20 Share Consolidation (PTLE)"
        result = alert_channel_message(message)

        self.assertEqual(result["ticker"], "PTLE")
        self.assertTrue(result["reverse_split_confirmed"])

    def test_reverse_split_with_url_uses_remote_consolidation_detection(self) -> None:
        message = "PTLE update https://example.com/news"

        with (
            patch("utils.parsing_utils._extract_ticker_from_remote_source", return_value="PTLE"),
            patch(
                "utils.parsing_utils._remote_contains_reverse_split",
                return_value=(True, r"(?:share|stock)\\s+consolidation"),
            ),
        ):
            result = alert_channel_message(message)

        self.assertEqual(result["ticker"], "PTLE")
        self.assertTrue(result["reverse_split_confirmed"])

    def test_reverse_split_parses_tsx_venture_suffix_ticker_without_false_match(self) -> None:
        message = (
            "TORONTO, ON / ACCESS Newswire / March 11, 2026 / Alturas Minerals Corp. "
            "(TSX-V:ALT.V) is pleased to announce that the Company will be seeking "
            "shareholder approval for a consolidation of the Company's outstanding "
            "common shares."
        )

        result = alert_channel_message(message)

        self.assertEqual(result["ticker"], "ALT")
        self.assertTrue(result["reverse_split_confirmed"])

    def test_reverse_split_does_not_treat_single_letter_parenthetical_as_ticker(self) -> None:
        message = "Company announces reverse split on the basis of up to 1-for-10 (the \"Shares\")"

        result = alert_channel_message(message)

        self.assertIsNone(result["ticker"])
        self.assertTrue(result["reverse_split_confirmed"])


class ParseOrderMessageTest(unittest.TestCase):
    def test_robinhood_mfa_prompt_is_treated_as_notification(self) -> None:
        message = (
            "Robinhood 2: Check phone app for verification prompt. "
            "You have ~60 seconds."
        )

        with (
            patch("utils.parsing_utils.logger.error") as error_mock,
            patch("utils.parsing_utils.logger.info") as info_mock,
        ):
            parse_order_message(message)

        error_mock.assert_not_called()
        info_mock.assert_called()

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
