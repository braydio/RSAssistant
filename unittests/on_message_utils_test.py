"""Tests for helper utilities in :mod:`rsassistant.bot.handlers.on_message`."""

import unittest

from rsassistant.bot.handlers.on_message import (
    _format_account_label,
    _resolve_fractional_handling_text,
    _resolve_round_up_confirmation,
    _resolve_round_up_snippet,
    format_mentions,
)


class OnMessageUtilsTest(unittest.TestCase):
    def test_format_mentions_respects_enabled_flag(self):
        ids = ["123", "456"]
        self.assertEqual(format_mentions(ids, enabled=True), "<@123> <@456> ")
        self.assertEqual(format_mentions(ids, enabled=False), "")
        self.assertEqual(
            format_mentions(ids, enabled=False, force=True), "<@123> <@456> "
        )
        self.assertEqual(format_mentions([], enabled=True), "")

    def test_resolve_round_up_snippet_prefers_existing_snippet(self):
        policy_info = {
            "snippet": (
                " Fractional shares will be rounded up to the nearest whole share. "
            )
        }
        result = _resolve_round_up_snippet(policy_info, max_length=80)
        self.assertEqual(
            result, "Fractional shares will be rounded up to the nearest whole share."
        )

    def test_resolve_round_up_snippet_extracts_from_body_text(self):
        body_text = (
            "The company confirms fractional shares will be rounded up to the "
            "nearest whole share."
        )
        result = _resolve_round_up_snippet(
            {"body_text": body_text}, max_length=60
        )
        self.assertIn("fractional shares will be rounded up", result)
        self.assertLessEqual(len(result), 60)

    def test_resolve_round_up_snippet_rejects_nearest_only(self):
        body_text = "Fractional shares will be rounded to the nearest whole share."
        self.assertIsNone(
            _resolve_round_up_snippet({"body_text": body_text}, max_length=100)
        )

    def test_format_account_label_skips_duplicate_broker_prefix(self):
        self.assertEqual(
            _format_account_label("Schwab", "Schwab 1 8745"), "Schwab 1 8745"
        )
        self.assertEqual(_format_account_label("Schwab", "1 8745"), "Schwab 1 8745")

    def test_resolve_round_up_requires_accepted_explicit_policy(self):
        policy_info = {
            "round_up_confirmed": False,
            "llm_policy_accepted": True,
            "llm_details": {"fractional_share_policy": "rounded_up"},
        }
        self.assertTrue(_resolve_round_up_confirmation(policy_info))

        policy_info["llm_details"][
            "fractional_share_policy"
        ] = "rounded_to_nearest_whole"
        self.assertFalse(_resolve_round_up_confirmation(policy_info))

    def test_resolve_round_up_rejects_reconciliation_conflict(self):
        policy_info = {
            "round_up_confirmed": True,
            "reconciliation_conflicts": [{"field": "fractional_share_policy"}],
        }
        self.assertFalse(_resolve_round_up_confirmation(policy_info))

    def test_resolve_round_up_falls_back_to_programmatic(self):
        self.assertTrue(_resolve_round_up_confirmation({"round_up_confirmed": True}))

    def test_rejected_llm_policy_is_not_displayed_as_resolved(self):
        policy_info = {
            "llm_policy_accepted": False,
            "llm_details": {"fractional_share_policy": "rounded_up"},
            "sec_policy": "Fractional shares will be paid out in cash.",
        }
        self.assertEqual(
            _resolve_fractional_handling_text(policy_info),
            "Fractional shares will be paid out in cash.",
        )


if __name__ == "__main__":
    unittest.main()
