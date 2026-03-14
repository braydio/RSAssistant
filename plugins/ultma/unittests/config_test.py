"""Tests for ULT-MA plugin environment configuration."""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

STAGING_ROOT = Path(__file__).resolve().parents[3]
if str(STAGING_ROOT) not in sys.path:
    sys.path.insert(0, str(STAGING_ROOT))


class UltmaConfigTest(unittest.TestCase):
    """Validate that plugin config is resolved from process environment only."""

    def _reload_config_module(self):
        module_name = "plugins.ultma.config"
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)

    def test_config_uses_process_environment_values(self):
        """Load settings directly from process environment variables."""

        with mock.patch.dict(
            os.environ,
            {
                "ENABLE_AUTOMATED_TRADING": "true",
                "TRADING_TRAILING_BUFFER": "0.15",
                "TRADING_PRICE_CHECK_INTERVAL_SECONDS": "120",
                "TRADING_BROKERS": "Fidelity, Schwab",
                "AUTO_RSA_BASE_URL": "https://example.local",
                "AUTO_RSA_API_KEY": "secret",
            },
            clear=False,
        ):
            config = self._reload_config_module()

        self.assertTrue(config.ENABLE_AUTOMATED_TRADING)
        self.assertEqual(0.15, config.TRADING_TRAILING_BUFFER)
        self.assertEqual(120, config.TRADING_PRICE_CHECK_INTERVAL_SECONDS)
        self.assertEqual(["Fidelity", "Schwab"], config.TRADING_BROKERS)
        self.assertEqual("https://example.local", config.AUTO_RSA_BASE_URL)
        self.assertEqual("secret", config.AUTO_RSA_API_KEY)

    def test_config_does_not_load_plugin_local_env_files(self):
        """Ignore ULTMA_ENV_FILE and rely on process environment only."""

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("TRADING_TRAILING_BUFFER=0.99\n")

            with mock.patch.dict(
                os.environ,
                {
                    "ULTMA_ENV_FILE": str(env_path),
                    "TRADING_TRAILING_BUFFER": "0.07",
                },
                clear=False,
            ):
                config = self._reload_config_module()

        self.assertEqual(0.07, config.TRADING_TRAILING_BUFFER)


if __name__ == "__main__":
    unittest.main()
