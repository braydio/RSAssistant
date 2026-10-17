import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence import broker_incidents as bi
from rsassistant.services.broker_health import Level, Status, classify_error, scrub


class ScrubTest(unittest.TestCase):
    def test_secrets_urls_html_and_account_numbers_removed(self):
        out = scrub("password=hunter2 token: abc123 https://x.test/cb?state=zz "
                    "code 945538 acct 123456789 <html><body>secret</body></html>")
        for leaked in ("hunter2", "abc123", "state=zz", "945538", "123456789", "secret"):
            self.assertNotIn(leaked, out)
        self.assertIn("6789", scrub("acct 123456789"))


class ClassifyTest(unittest.TestCase):
    def test_levels(self):
        cases = {
            "Failed to connect to browser": (Level.INFRASTRUCTURE, "browser_launch"),
            "Driver not found": (Level.INFRASTRUCTURE, "browser_launch"),
            "Waiting for device approval on your phone": (Level.ACCOUNT, "challenge"),
            "HTTP 429 Too Many Requests": (Level.ADAPTER, "rate_limited"),
            "Page.goto timeout 30000ms": (Level.ADAPTER, "timeout"),
            "invalid password": (Level.ACCOUNT, "auth"),
            "no such element: #submit": (Level.ADAPTER, "adapter_error"),
            "something odd": (Level.ADAPTER, "unclassified"),
        }
        for text, (level, cls) in cases.items():
            got = classify_error(text)
            self.assertEqual((got.level, got.error_class), (level, cls), text)

    def test_ambiguous_execution_blocks_and_challenge_status(self):
        c = classify_error("order button clicked but confirmation not detected")
        self.assertTrue(c.blocks_new_orders)
        self.assertEqual(classify_error("SMS code required").status, Status.CHALLENGE_PENDING)


class IncidentRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "t.db")

    def test_shared_browser_failure_is_one_infra_incident(self):
        for p in ("fidelity:1", "chase:1", "wellsfargo:1"):
            bi.report_failure(p, "Failed to connect to browser", database=self.db)
        open_ = bi.open_incidents(database=self.db)
        self.assertEqual(len(open_), 1)
        self.assertEqual(open_[0]["level"], "infrastructure")
        self.assertEqual(open_[0]["affected_profiles"], 3)
        self.assertEqual(open_[0]["occurrences"], 3)

    def test_duplicates_dedupe_per_profile_and_recovery_closes(self):
        a = bi.report_failure("fennel:1", "HTTP 429", database=self.db)
        b = bi.report_failure("fennel:1", "429 too many requests", database=self.db)
        self.assertTrue(a["created"] and not b["created"])
        self.assertEqual(bi.record_success("fennel:1", database=self.db), 1)
        self.assertEqual(bi.open_incidents(database=self.db), [])

    def test_recovery_does_not_close_infra_or_ambiguous_hold(self):
        bi.report_failure("fidelity:1", "Failed to connect to browser", database=self.db)
        r = bi.report_failure("fidelity:1", "order button clicked but confirmation not detected",
                              database=self.db)
        self.assertTrue(bi.is_profile_blocked("fidelity:1", database=self.db))
        self.assertEqual(bi.record_success("fidelity:1", database=self.db), 0)
        self.assertTrue(bi.is_profile_blocked("fidelity:1", database=self.db))
        self.assertTrue(bi.resolve_incident(r["incident_id"], database=self.db))
        self.assertFalse(bi.is_profile_blocked("fidelity:1", database=self.db))
        self.assertEqual(len(bi.open_incidents(database=self.db)), 1)  # infra remains

    def test_stored_detail_is_scrubbed(self):
        bi.report_failure("x:1", "login failed password=hunter2 for 123456789", database=self.db)
        from rsassistant.persistence.db import connect_runtime_db
        conn = connect_runtime_db(self.db)
        detail = conn.execute("SELECT detail FROM broker_incident_events").fetchone()[0]
        conn.close()
        self.assertNotIn("hunter2", detail)
        self.assertNotIn("123456789", detail)


if __name__ == "__main__":
    unittest.main()
