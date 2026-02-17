"""Tests for startup messaging helpers in ``rsassistant.bot.core``."""

from __future__ import annotations

import unittest

from rsassistant.bot import core


class CoreStartupMessageTest(unittest.TestCase):
    """Validate startup guidance text for account-mapping setup."""

    def test_build_account_setup_message_references_sql_and_csv_flow(self):
        """Missing-mapping guidance should direct users to SQL and CSV outputs."""

        message = core._build_account_setup_message()

        self.assertIn("SQL", message)
        self.assertIn("CSV", message)
        self.assertIn("..loadmap", message)


if __name__ == "__main__":
    unittest.main()
