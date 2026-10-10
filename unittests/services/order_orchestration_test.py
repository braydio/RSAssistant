"""Plain-value tests for Discord-independent order planning."""

import unittest

from rsassistant.services import order_orchestration


class OrderOrchestrationTests(unittest.TestCase):
    def test_watchlist_autobuy_plan_filters_duplicates_and_ignored_brokers(self):
        planned, skipped = order_orchestration.build_watchlist_autobuy_commands(
            {
                "Schwab Main (123)": ["AAA", "BBB", "AAA"],
                "Ignored Main (456)": ["CCC"],
            },
            {("AAA", "schwab")},
            {"ignored"},
        )
        self.assertEqual(planned, [("BBB", "SCHWAB", "!rsa buy 1 BBB SCHWAB false")])
        self.assertEqual(skipped, [("AAA", "SCHWAB")])

    def test_autobuy_specs_preserve_standard_and_override_defaults(self):
        orders = order_orchestration.build_autobuy_orders(
            "test",
            3,
            {
                "standard_order": {"quantity": 5},
                "overrides": [{"broker": " Schwab "}, {"broker": ""}],
            },
        )
        self.assertEqual(
            orders,
            [
                {
                    "ticker": "test",
                    "broker": "all not Schwab",
                    "quantity": 5,
                    "kind": "standard",
                    "excluded_brokers": ["Schwab"],
                },
                {
                    "ticker": "test",
                    "broker": "Schwab",
                    "quantity": 3,
                    "kind": "override",
                    "excluded_brokers": [],
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
