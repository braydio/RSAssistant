import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import holdings_importer


class HoldingsImporterTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.snapshot_path = Path(self.temp_dir.name) / "holdings.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_replaces_live_snapshot(self):
        self.snapshot_path.write_text(
            json.dumps(
                [
                    {
                        "broker": "Broker",
                        "group": "1",
                        "account": "A1",
                        "ticker": "NEW",
                        "quantity": 1,
                        "price": 10,
                    }
                ]
            )
        )
        calls = []

        def fake_save(rows, **kwargs):
            calls.append((rows, kwargs))
            return True

        with (
            patch.object(holdings_importer, "AUTO_RSA_HOLDINGS_ENABLED", True),
            patch.object(holdings_importer, "save_holdings_to_csv", fake_save),
        ):
            self.assertEqual(holdings_importer.import_holdings_file(self.snapshot_path), 1)

        self.assertEqual(
            calls[0][1],
            {"use_refresh_target": False, "replace_existing": True},
        )
        self.assertEqual(calls[0][0][0]["ticker"], "NEW")

    def test_import_allows_valid_empty_snapshot(self):
        self.snapshot_path.write_text("[]")
        calls = []

        with (
            patch.object(holdings_importer, "AUTO_RSA_HOLDINGS_ENABLED", True),
            patch.object(
                holdings_importer,
                "save_holdings_to_csv",
                lambda rows, **kwargs: calls.append((rows, kwargs)) or True,
            ),
        ):
            self.assertEqual(holdings_importer.import_holdings_file(self.snapshot_path), 0)

        self.assertEqual(
            calls,
            [([], {"use_refresh_target": False, "replace_existing": True})],
        )

    def test_import_if_updated_retries_failed_save(self):
        self.snapshot_path.write_text("[]")
        calls = {"count": 0}

        def fake_import(_path):
            calls["count"] += 1
            return -1 if calls["count"] == 1 else 0

        with (
            patch.object(holdings_importer, "AUTO_RSA_HOLDINGS_ENABLED", True),
            patch.object(holdings_importer, "_last_import_mtime", None),
            patch.object(holdings_importer, "import_holdings_file", fake_import),
        ):
            self.assertEqual(
                holdings_importer.import_holdings_if_updated(self.snapshot_path), -1
            )
            self.assertEqual(
                holdings_importer.import_holdings_if_updated(self.snapshot_path), 0
            )

        self.assertEqual(calls["count"], 2)

    def test_import_rejects_partially_invalid_snapshot(self):
        self.snapshot_path.write_text(
            json.dumps(
                [
                    {
                        "broker": "Broker",
                        "group": "1",
                        "account": "A1",
                        "ticker": "GOOD",
                    },
                    {"broker": "Broker", "ticker": "MISSING_ACCOUNT"},
                ]
            )
        )

        with (
            patch.object(holdings_importer, "AUTO_RSA_HOLDINGS_ENABLED", True),
            patch.object(holdings_importer, "save_holdings_to_csv") as save_mock,
        ):
            self.assertEqual(holdings_importer.import_holdings_file(self.snapshot_path), -1)

        save_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
