import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import holdings_importer as hi

ENTRY = {"broker": "b", "group": "1", "account": "9", "ticker": "AAA", "quantity": 1}


class HoldingsImporterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "h.json"
        hi._last_import_fingerprint = None
        hi._last_failure_fingerprint = None
        hi._missing_warned = False
        p = mock.patch.object(hi, "AUTO_RSA_HOLDINGS_ENABLED", True)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        s = mock.patch.object(hi, "save_holdings_to_csv")
        self.save = s.start()
        self.addCleanup(s.stop)

    def write(self, payload, mtime_ns=None):
        self.path.write_text(json.dumps(payload))
        if mtime_ns is not None:
            os.utime(self.path, ns=(mtime_ns, mtime_ns))

    def test_unchanged_snapshot_not_reimported(self):
        self.write([ENTRY])
        self.assertEqual(hi.import_holdings_if_updated(self.path), 1)
        self.assertEqual(hi.import_holdings_if_updated(self.path), 0)
        self.assertEqual(self.save.call_count, 1)

    def test_equal_mtime_changed_size_reimports(self):
        self.write([ENTRY], mtime_ns=10**18)
        hi.import_holdings_if_updated(self.path)
        self.write([ENTRY, {**ENTRY, "ticker": "BBB"}], mtime_ns=10**18)
        self.assertEqual(hi.import_holdings_if_updated(self.path), 2)

    def test_invalid_json_retried_after_fix_without_mtime_change(self):
        self.path.write_text("{bad")
        self.assertEqual(hi.import_holdings_if_updated(self.path), 0)
        self.assertIsNone(hi._last_import_fingerprint)
        self.write([ENTRY])
        self.assertEqual(hi.import_holdings_if_updated(self.path), 1)

    def test_zero_valid_rows_not_acknowledged(self):
        self.write([{"broker": ""}])
        self.assertEqual(hi.import_holdings_if_updated(self.path), 0)
        self.assertIsNone(hi._last_import_fingerprint)

    def test_write_failure_retries(self):
        self.write([ENTRY])
        self.save.side_effect = OSError("disk")
        self.assertEqual(hi.import_holdings_if_updated(self.path), 0)
        self.save.side_effect = None
        self.assertEqual(hi.import_holdings_if_updated(self.path), 1)

    def test_file_changed_during_read_rejected(self):
        self.write([ENTRY])
        real = hi._fingerprint
        calls = []

        def flaky(p):
            calls.append(1)
            fp = real(p)
            return fp if len(calls) != 3 else (fp[0] + 1, fp[1])

        with mock.patch.object(hi, "_fingerprint", flaky):
            self.assertEqual(hi.import_holdings_if_updated(self.path), 0)
        self.save.assert_not_called()
        self.assertEqual(hi.import_holdings_if_updated(self.path), 1)

    def test_missing_warns_once_then_recovers(self):
        with self.assertLogs(hi.logger, "WARNING") as logs:
            hi.import_holdings_if_updated(self.path)
            hi.import_holdings_if_updated(self.path)
        self.assertEqual(len(logs.records), 1)
        self.write([ENTRY])
        self.assertEqual(hi.import_holdings_if_updated(self.path), 1)

    def test_disabled_mode(self):
        self.write([ENTRY])
        with mock.patch.object(hi, "AUTO_RSA_HOLDINGS_ENABLED", False):
            self.assertEqual(hi.import_holdings_if_updated(self.path), 0)
            self.assertEqual(hi.import_holdings_file(self.path), 0)
        self.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
