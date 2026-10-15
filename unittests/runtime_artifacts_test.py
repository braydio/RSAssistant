import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_runtime_artifacts.py"
spec = importlib.util.spec_from_file_location("audit_runtime_artifacts", SCRIPT)
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def _touch(path: Path, age_days: float, data: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - age_days * 86400
    os.utime(path, (t, t))


class AuditRuntimeArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vol = Path(self.tmp.name) / "volumes"
        _touch(self.vol / "db/fidelity_errors/old.html", 40)
        _touch(self.vol / "db/fidelity_errors/new.png", 1)
        _touch(self.vol / "logs/app.log.1", 40)
        _touch(self.vol / "logs/app.log", 40)
        _touch(self.vol / "cache/x.json.123.tmp", 40)
        _touch(self.vol / "cache/yfinance_price_cache.json", 40)
        for protected in (
            "db/rsa_database.db", "db/rsa_database.db-wal", "db/rsa_database.db-shm",
            "db/order_send_log.json.migrated", "logs/holdings_log.csv",
            "logs/orders_log.csv", "db/rsa_database.db.bak-1",
        ):
            _touch(self.vol / protected, 400)

    def names(self):
        return {str(p.relative_to(self.vol)) for p in self.vol.rglob("*") if p.is_file()}

    def test_dry_run_mutates_nothing(self):
        before = self.names()
        self.assertEqual(audit.main(["--volumes-dir", str(self.vol)]), 0)
        self.assertEqual(self.names(), before)

    def test_prune_requires_age(self):
        with self.assertRaises(SystemExit):
            audit.main(["--volumes-dir", str(self.vol), "--prune"])
        with self.assertRaises(SystemExit):
            audit.main(["--volumes-dir", str(self.vol), "--prune", "--older-than-days", "0"])

    def test_prune_scope_and_protection(self):
        audit.main(["--volumes-dir", str(self.vol), "--prune", "--older-than-days", "30"])
        left = self.names()
        self.assertNotIn("db/fidelity_errors/old.html", left)
        self.assertNotIn("logs/app.log.1", left)
        self.assertNotIn("cache/x.json.123.tmp", left)
        for kept in (
            "db/fidelity_errors/new.png", "logs/app.log", "cache/yfinance_price_cache.json",
            "db/rsa_database.db", "db/rsa_database.db-wal", "db/rsa_database.db-shm",
            "db/order_send_log.json.migrated", "logs/holdings_log.csv",
            "logs/orders_log.csv", "db/rsa_database.db.bak-1",
        ):
            self.assertIn(kept, left)

    def test_symlinks_not_followed_or_deleted(self):
        outside = Path(self.tmp.name) / "outside.html"
        _touch(outside, 400)
        link = self.vol / "db/fidelity_errors/link.html"
        link.symlink_to(outside)
        linked_dir = Path(self.tmp.name) / "elsewhere"
        _touch(linked_dir / "a.log.1", 400)
        (self.vol / "cache").rename(self.vol / "cache_real")
        (self.vol / "cache").symlink_to(linked_dir)
        audit.main(["--volumes-dir", str(self.vol), "--prune", "--older-than-days", "30"])
        self.assertTrue(outside.exists())
        self.assertTrue(link.is_symlink())
        self.assertTrue((linked_dir / "a.log.1").exists())


if __name__ == "__main__":
    unittest.main()
