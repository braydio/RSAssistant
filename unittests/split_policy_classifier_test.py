import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence import split_policy_evidence as repo
from rsassistant.services import split_policy_classifier as sp
from rsassistant.services.split_policy_classifier import Evidence, Policy, classify

SEC = "sec_filing"


class ClassifyTest(unittest.TestCase):
    def test_nearest_whole_is_not_unconditional_round_up(self):
        d = classify([Evidence(SEC, "rounded_to_nearest_whole")], effective_date="2026-10-19")
        self.assertEqual(d.policy, Policy.ROUND_TO_NEAREST)
        self.assertFalse(d.auto_executable)

    def test_round_up_needs_primary_source_and_effective_date(self):
        ok = classify([Evidence(SEC, "rounded_up", "registered_holder")], effective_date="2026-10-19")
        self.assertTrue(ok.auto_executable)
        self.assertFalse(classify([Evidence(SEC, "rounded_up")], effective_date=None).auto_executable)
        llm_only = classify([Evidence("llm", "rounded_up")], effective_date="2026-10-19")
        self.assertEqual(llm_only.policy, Policy.ROUND_UP_UNCONDITIONAL)
        self.assertFalse(llm_only.auto_executable)

    def test_llm_never_overrides_contrary_primary_clause(self):
        d = classify([Evidence(SEC, "cash_in_lieu"), Evidence("llm", "rounded_up")],
                     effective_date="2026-10-19")
        self.assertEqual(d.policy, Policy.CASH_IN_LIEU)
        self.assertFalse(d.auto_executable)
        self.assertEqual(len(d.contrary), 1)

    def test_conflicting_primary_sources(self):
        d = classify([Evidence(SEC, "rounded_up"), Evidence("issuer_release", "rounded_down")],
                     effective_date="2026-10-19")
        self.assertEqual(d.policy, Policy.CONFLICT)
        self.assertFalse(d.auto_executable)

    def test_unknown_when_no_evidence(self):
        self.assertEqual(classify([], effective_date="x").policy, Policy.UNKNOWN)
        self.assertEqual(classify([Evidence(SEC, "unclear")], effective_date="x").policy, Policy.UNKNOWN)

    def test_dedupe_key_uses_action_identity_not_ticker(self):
        a = sp.corporate_action_key("Acme Corp.", "1-for-10", "2026-10-19")
        b = sp.corporate_action_key("ACME CORP", "1 for 10", "2026-10-19")
        c = sp.corporate_action_key("Acme Corp.", "1-for-10", "2027-01-05")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class EvidenceRepoTest(unittest.TestCase):
    def test_idempotent_and_ordered(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "t.db")
            e = Evidence(SEC, "rounded_up", "dtc_participant", "fractions rounded up", "u")
            self.assertTrue(repo.record_evidence("abc", "2026-10-19", e, database=db))
            self.assertFalse(repo.record_evidence("ABC", "2026-10-19", e, database=db))
            self.assertEqual(repo.load_evidence("ABC", "2026-10-19", database=db), [e])


if __name__ == "__main__":
    unittest.main()
