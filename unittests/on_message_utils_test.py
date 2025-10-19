"""Unit tests for Discord holdings alert aggregation helpers."""

import unittest

from utils import on_message_utils as omu
from utils.on_message_utils import format_mentions


class FormatMentionsTest(unittest.TestCase):
    """Validate mention formatting helper behaviour."""

    def test_format_mentions_respects_enabled_flag(self) -> None:
        """Mentions should respect the enabled flag unless forced."""

        ids = ["123", "456"]
        self.assertEqual(format_mentions(ids, enabled=True), "<@123> <@456> ")
        self.assertEqual(format_mentions(ids, enabled=False), "")
        self.assertEqual(
            format_mentions(ids, enabled=False, force=True), "<@123> <@456> "
        )
        self.assertEqual(format_mentions([], enabled=True), "")


class GroupAlertEntriesTest(unittest.TestCase):
    """Validate holdings alert grouping by broker and account."""

    def test_group_alert_entries_by_broker_and_account(self) -> None:
        """Entries should be grouped under their broker and account names."""

        entries = [
            {
                "broker": "Webull",
                "account_name": "Alpha",
                "ticker": "AAA",
                "price": 12.5,
                "quantity": 5,
            },
            {
                "broker": "Webull",
                "account_name": "Beta",
                "ticker": "BBB",
                "price": 8.0,
                "quantity": 2,
            },
            {
                "broker": "Fidelity",
                "account_name": "Core",
                "ticker": "CCC",
                "price": 3.5,
                "quantity": 1,
            },
        ]

        grouped = omu._group_alert_entries(entries)

        self.assertEqual(set(grouped.keys()), {"Webull", "Fidelity"})
        self.assertEqual(set(grouped["Webull"].keys()), {"Alpha", "Beta"})
        self.assertEqual(grouped["Fidelity"]["Core"][0]["ticker"], "CCC")


class FormatAlertSummaryTest(unittest.TestCase):
    """Ensure holdings summaries are concise and grouped by broker."""

    def test_format_alert_summary_collapse_broker_repetition(self) -> None:
        """Summary output should list each broker once with nested accounts."""

        grouped = {
            "Webull": {
                "Alpha": [
                    {"ticker": "AAA", "price": 10.0, "quantity": 1},
                    {"ticker": "ZZZ", "price": 9.5, "quantity": 4},
                ],
                "Beta": [
                    {"ticker": "BBB", "price": 7.0, "quantity": 2},
                ],
            }
        }

        chunks = omu._format_alert_summary(grouped, threshold=5.0, mention="")

        self.assertTrue(chunks)
        first_chunk = chunks[0]
        self.assertIn("Detected holdings >= $5.00 across 2 account(s):", first_chunk)
        self.assertEqual(first_chunk.count("- Webull"), 1)
        self.assertIn("Alpha: AAA @ $10.00 (qty 1), ZZZ @ $9.50 (qty 4)", first_chunk)
        self.assertIn("Beta: BBB @ $7.00 (qty 2)", first_chunk)


if __name__ == "__main__":
    unittest.main()
