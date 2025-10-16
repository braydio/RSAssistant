import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import config_utils
from utils import on_message_utils


class TaggedAlertConfigTests(unittest.TestCase):
    """Validate tagged alert configuration parsing from env and files."""

    def test_requirements_from_env_and_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "tagged_alerts.txt"
            config_path.write_text("AAPL:50\nmsft\n", encoding="utf-8")
            env_vars = {
                "TAGGED_ALERT_TICKERS": "TSLA:5, GOOG, AAPL:10",
                "TAGGED_ALERTS_FILE": str(config_path),
            }
            try:
                with mock.patch.dict(os.environ, env_vars, clear=False):
                    reloaded = importlib.reload(config_utils)
                    self.assertEqual(
                        reloaded.TAGGED_ALERT_REQUIREMENTS,
                        {
                            "AAPL": 10.0,
                            "MSFT": None,
                            "TSLA": 5.0,
                            "GOOG": None,
                        },
                    )
            finally:
                importlib.reload(config_utils)


class TaggedAlertDecisionTests(unittest.TestCase):
    """Ensure mention decisions respect tagged alert requirements."""

    def test_should_tag_alerts_based_on_requirements(self):
        original_requirements = on_message_utils.TAGGED_ALERT_REQUIREMENTS
        try:
            on_message_utils.TAGGED_ALERT_REQUIREMENTS = {
                "AAPL": 10.0,
                "MSFT": None,
            }
            self.assertTrue(on_message_utils._should_tag_alert("AAPL", 10))
            self.assertTrue(on_message_utils._should_tag_alert("AAPL", 12.5))
            self.assertFalse(on_message_utils._should_tag_alert("AAPL", 5))
            self.assertTrue(on_message_utils._should_tag_alert("MSFT", 1))
            self.assertFalse(on_message_utils._should_tag_alert("TSLA", 100))

            entries = [
                {"ticker": "AAPL", "quantity": 15},
                {"ticker": "MSFT", "quantity": 0},
            ]
            self.assertTrue(on_message_utils._should_tag_entries(entries))

            limited_entries = [{"ticker": "AAPL", "quantity": 5}]
            self.assertFalse(on_message_utils._should_tag_entries(limited_entries))

            self.assertFalse(on_message_utils._should_tag_entries([]))
        finally:
            on_message_utils.TAGGED_ALERT_REQUIREMENTS = original_requirements


if __name__ == "__main__":
    unittest.main()
