"""Plain-value contracts for extracted alert-processing service functions."""

import unittest

from rsassistant.services import alert_processing


class AlertProcessingTests(unittest.TestCase):
    def test_tagging_uses_case_insensitive_ticker_and_threshold(self):
        requirements = {"AAPL": 10, "MSFT": None}
        self.assertTrue(alert_processing.should_tag_alert("aapl", 10, requirements))
        self.assertFalse(alert_processing.should_tag_alert("AAPL", 9, requirements))
        self.assertTrue(alert_processing.should_tag_alert("msft", 0, requirements))
        self.assertFalse(alert_processing.should_tag_alert("TSLA", 100, requirements))

    def test_missing_tickers_are_grouped_and_sorted_by_account(self):
        holdings = [
            {"broker": "Test Broker", "account_name": "1", "account": "123", "ticker": "BBB"},
            {"broker": "Test Broker", "account_name": "1", "account": "123", "ticker": "AAA"},
        ]
        self.assertEqual(
            alert_processing.compute_account_missing_tickers(holdings, {"AAA", "CCC"}),
            {"Test Broker 1 (123)": ["CCC"]},
        )

    def test_watch_date_accepts_iso_datetime_and_leaves_other_values(self):
        self.assertEqual(
            alert_processing.format_watch_date("2026-10-08T14:30:00"), "10/8"
        )
        self.assertEqual(alert_processing.format_watch_date("soon"), "soon")

    def test_holdings_alert_collection_uses_injected_boundaries(self):
        calls = []
        holdings = [
            {
                "ticker": "AREB",
                "broker": "Schwab",
                "account_name": "Main",
                "price": 2,
                "quantity": 51,
            },
            {
                "ticker": "TEST",
                "broker": "Schwab",
                "account_name": "Main",
                "price": 3,
                "quantity": 1,
            },
        ]

        result = alert_processing.collect_holdings_alert_data(
            holdings,
            threshold=1,
            ignored_tickers=set(),
            is_broker_ignored=lambda broker: False,
            is_tracked_reverse_split=lambda ticker: ticker == "TEST",
            record_action_today=lambda broker, account, ticker: calls.append(
                (broker, account, ticker)
            )
            or True,
            areb_ticker="AREB",
            areb_quantity_threshold=50,
            auto_sell=True,
        )

        self.assertEqual(len(result["areb_alerts"]), 1)
        self.assertEqual(result["one_share_positions"], [("Schwab", "TEST", 3.0)])
        self.assertTrue(result["reverse_split_round_ups_found"])
        self.assertEqual(result["sell_commands"], ["!rsa sell 51.0 AREB Schwab false", "!rsa sell 1.0 TEST Schwab false"])
        self.assertEqual(
            calls,
            [
                ("Schwab", "Main", "AREB_AREB_THRESHOLD"),
                ("Schwab", "Main", "AREB"),
                ("Schwab", "Main", "TEST"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
