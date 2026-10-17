import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence import holdings as repo
from rsassistant.persistence.schema import LATEST_SCHEMA_VERSION


class HoldingsImportLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "t.db")

    def _rec(self, sha, status, **kw):
        return repo.record_holdings_import(
            source_path="/x.json", source_sha256=sha, source_mtime=None,
            record_count=3, account_count=2, status=status, database=self.db, **kw,
        )

    def test_schema_version_and_latest_success(self):
        self.assertIsNone(repo.last_successful_import_sha(database=self.db))
        self._rec("a" * 64, "succeeded")
        self._rec("b" * 64, "failed", error="boom")
        self.assertEqual(repo.last_successful_import_sha(database=self.db), "a" * 64)
        self.assertEqual(LATEST_SCHEMA_VERSION, 13)

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError):
            self._rec("c" * 64, "bogus")
