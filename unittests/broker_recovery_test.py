import os
import socket
import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence import broker_incidents as bi
from rsassistant.services import broker_recovery as br
from rsassistant.services.broker_health import classify_error


class PlanTest(unittest.TestCase):
    def test_browser_restart_is_bounded_then_escalates(self):
        c = classify_error("Failed to connect to browser")
        self.assertEqual(br.plan_recovery(c).action, br.Action.RESTART_BROWSER_ONCE)
        p = br.plan_recovery(c, {br.Action.RESTART_BROWSER_ONCE: 1})
        self.assertEqual(p.action, br.Action.ESCALATE_CODE_REGRESSION)

    def test_rate_limit_honours_retry_after_with_backoff_then_cooldown(self):
        c = classify_error("HTTP 429")
        p0 = br.plan_recovery(c, retry_after=30)
        p1 = br.plan_recovery(c, {br.Action.WAIT_RETRY_AFTER: 1}, retry_after=30)
        self.assertEqual((p0.delay_seconds, p1.delay_seconds), (30, 60))
        self.assertEqual(br.plan_recovery(c, {br.Action.WAIT_RETRY_AFTER: 3}).action, br.Action.COOLDOWN)

    def test_ambiguous_execution_never_retries(self):
        c = classify_error("order button clicked but confirmation not detected")
        self.assertEqual(br.plan_recovery(c).action, br.Action.RECONCILE_BEFORE_ANYTHING)

    def test_challenge_and_auth_go_to_operator(self):
        self.assertEqual(br.plan_recovery(classify_error("device approval")).action,
                         br.Action.REQUEST_OPERATOR_CHALLENGE)
        self.assertEqual(br.plan_recovery(classify_error("login failed")).action,
                         br.Action.REQUEST_REAUTH)


class SingleFlightTest(unittest.TestCase):
    def test_one_recovery_per_profile(self):
        sf = br.SingleFlight()
        self.assertTrue(sf.try_acquire("a"))
        self.assertFalse(sf.try_acquire("a"))
        self.assertTrue(sf.try_acquire("b"))
        sf.release("a")
        self.assertTrue(sf.try_acquire("a"))


class ChallengeTest(unittest.TestCase):
    def test_single_use_and_expiry(self):
        now = [0.0]
        store = br.ChallengeStore(ttl_seconds=10, clock=lambda: now[0])
        t = store.issue("wellsfargo:1")
        self.assertEqual(store.redeem(t), "wellsfargo:1")
        self.assertIsNone(store.redeem(t))
        t2 = store.issue("x")
        now[0] = 11
        self.assertIsNone(store.redeem(t2))
        self.assertIsNone(store.redeem("bogus"))


class LockCleanupTest(unittest.TestCase):
    def _lock(self, d, target):
        os.symlink(target, Path(d) / "SingletonLock")
        os.symlink("x", Path(d) / "SingletonCookie")

    def test_refuses_active_pid_and_foreign_host_removes_dead_local(self):
        host = socket.gethostname()
        with tempfile.TemporaryDirectory() as d:
            self._lock(d, f"{host}-{os.getpid()}")
            self.assertEqual(br.clean_stale_chromium_lock(d), "active")
            self.assertTrue((Path(d) / "SingletonLock").is_symlink())
        with tempfile.TemporaryDirectory() as d:
            self._lock(d, "archdesk-123")
            self.assertEqual(br.clean_stale_chromium_lock(d, hostname="container"), "foreign_host")
            self.assertTrue((Path(d) / "SingletonLock").is_symlink())
        with tempfile.TemporaryDirectory() as d:
            self._lock(d, f"{host}-999999999")
            self.assertEqual(br.clean_stale_chromium_lock(d), "removed")
            self.assertFalse((Path(d) / "SingletonLock").is_symlink())
            self.assertFalse((Path(d) / "SingletonCookie").is_symlink())
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(br.clean_stale_chromium_lock(d), "no_lock")


class CircuitBreakerTest(unittest.TestCase):
    def test_hold_blocks_orders_only_for_that_profile(self):
        with tempfile.TemporaryDirectory() as d:
            db = str(Path(d) / "t.db")
            self.assertTrue(br.may_submit_orders("fidelity:1", database=db))
            r = bi.report_failure("fidelity:1", "order button clicked but confirmation not detected", database=db)
            self.assertFalse(br.may_submit_orders("fidelity:1", database=db))
            self.assertTrue(br.may_submit_orders("fennel:1", database=db))
            bi.resolve_incident(r["incident_id"], database=db)
            self.assertTrue(br.may_submit_orders("fidelity:1", database=db))


if __name__ == "__main__":
    unittest.main()
