import unittest

from utils.policy_resolver import SplitPolicyResolver


def _details(**overrides):
    details = {
        "ticker": "ABC",
        "reverse_split_confirmed": True,
        "split_ratio": "1-10",
        "effective_date": "2026-10-31",
        "record_date": "2026-10-27",
        "fractional_share_policy": "rounded_up",
        "evidence": {
            "ticker": "ABC",
            "reverse_split": "ABC will effect a reverse stock split",
            "fractional_share_policy": "rounded up to the next whole share",
        },
    }
    details.update(overrides)
    return details


class PolicyLLMReconciliationTest(unittest.TestCase):
    def test_context_trim_preserves_complete_source_and_split_sentence(self):
        boilerplate = "Navigation sentence. " + ("x" * 330) + ". "
        notice = (
            "The Company will implement a 1-for-10 reverse stock split, effective "
            "July 20, 2026. Stockholders with fractional shares will be rounded up "
            "to the next whole share."
        )
        source = boilerplate + notice
        trimmed = SplitPolicyResolver._trim_to_context(source, "CIIT")

        self.assertEqual(trimmed, source)
        self.assertIn("1-for-10 reverse stock split", trimmed)

    def test_llm_fills_missing_fields_without_overwriting(self):
        result = {
            "effective_date": "2026-11-01",
            "policy": "Policy not clearly stated.",
        }
        SplitPolicyResolver._reconcile_llm_details(result, _details(), "ABC")

        self.assertEqual(result["effective_date"], "2026-11-01")
        self.assertEqual(result["record_date"], "2026-10-27")
        self.assertEqual(result["split_ratio"], "1-10")
        self.assertTrue(result["llm_details_accepted"])
        self.assertTrue(result["llm_policy_accepted"])
        self.assertTrue(result["round_up_confirmed"])
        self.assertEqual(
            result["reconciliation_conflicts"][0]["field"], "effective_date"
        )

    def test_ticker_mismatch_rejects_all_llm_fields(self):
        result = {"policy": "Policy not clearly stated."}
        SplitPolicyResolver._reconcile_llm_details(
            result, _details(ticker="XYZ"), "ABC"
        )
        self.assertFalse(result["llm_details_accepted"])
        self.assertNotIn("split_ratio", result)
        self.assertFalse(result["llm_policy_accepted"])
        self.assertIn("ticker mismatch", result["llm_rejection_reasons"][0])

    def test_rejection_identifies_reverse_evidence_failure(self):
        details = _details(reverse_split_confirmed=False)
        details["evidence"]["reverse_split"] = None
        details["evidence_validation_errors"] = [
            {"field": "reverse_split", "reason": "not_found_in_source"}
        ]
        result = {"policy": "Policy not clearly stated."}

        SplitPolicyResolver._reconcile_llm_details(result, details, "ABC")

        self.assertIn(
            "reverse split evidence not found in source",
            result["llm_rejection_reasons"],
        )

    def test_policy_conflict_preserves_programmatic_result(self):
        result = {
            "sec_policy": "Fractional shares will be paid out in cash.",
            "round_up_confirmed": False,
        }
        SplitPolicyResolver._reconcile_llm_details(result, _details(), "ABC")
        self.assertFalse(result["llm_policy_accepted"])
        self.assertFalse(result["round_up_confirmed"])
        self.assertEqual(
            result["reconciliation_conflicts"][-1]["field"],
            "fractional_share_policy",
        )

    def test_nearest_whole_does_not_confirm_round_up(self):
        result = {"policy": "Policy not clearly stated."}
        SplitPolicyResolver._reconcile_llm_details(
            result,
            _details(fractional_share_policy="rounded_to_nearest_whole"),
            "ABC",
        )
        self.assertTrue(result["llm_policy_accepted"])
        self.assertFalse(result["round_up_confirmed"])


if __name__ == "__main__":
    unittest.main()
