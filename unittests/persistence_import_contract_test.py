"""Contracts for direct persistence repositories and the legacy SQL facade."""

import ast
import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence import accounts, holdings, orders, reverse_splits, watchlists
from rsassistant.persistence.db import initialize_runtime_db
from utils import sql_utils


class PersistenceImportContractTest(unittest.TestCase):
    def test_compatibility_exports_delegate_to_domain_repositories(self):
        self.assertIs(
            sql_utils.fetch_account_mappings.__wrapped__,
            accounts.fetch_account_mappings,
        )
        self.assertIs(
            sql_utils.fetch_watchlist_entries.__wrapped__,
            watchlists.fetch_watchlist_entries,
        )
        self.assertIs(
            sql_utils.fetch_reverse_split_history.__wrapped__,
            reverse_splits.fetch_reverse_split_history,
        )
        self.assertIs(sql_utils.update_holdings_live_batch.__wrapped__, holdings.update_holdings_live_batch)
        self.assertEqual(sql_utils.insert_order_history.__module__, "utils.sql_utils")

    def test_persistence_domains_have_no_discord_imports(self):
        for module in (accounts, holdings, orders, reverse_splits, watchlists):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported = [node.module or ""]
                else:
                    continue
                self.assertFalse(
                    any(name == "discord" or name.startswith("discord.") for name in imported),
                    f"{module.__name__} imports Discord",
                )

    def test_direct_domain_repositories_share_runtime_schema(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            database = Path(temporary_dir) / "runtime.db"
            initialize_runtime_db(database)

            accounts.upsert_account_mapping("BrokerA", "1", "1234", "Primary", database=database)
            self.assertEqual(
                accounts.fetch_account_mappings(database=database),
                {"BrokerA": {"1": {"1234": "Primary"}}},
            )

            watchlists.upsert_watchlist_entry("ABC", "10/08", "1-5", database=database)
            self.assertEqual(
                watchlists.fetch_watchlist_entry("abc", database=database),
                {"split_date": "10/08", "split_ratio": "1-5"},
            )

            reverse_splits.insert_reverse_split_log_entry(
                "ABC", "1-5", "10/08", "test", database=database
            )
            self.assertEqual(
                reverse_splits.fetch_reverse_split_history("abc", database=database)[0]["source"],
                "test",
            )


if __name__ == "__main__":
    unittest.main()
