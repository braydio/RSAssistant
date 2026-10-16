"""Tests for durable split-event claims and order intents."""

import sqlite3
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path

from rsassistant.persistence import split_events as se
from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import LATEST_SCHEMA_VERSION, run_migrations


def _future(days=3):
    return (date.today() + timedelta(days=days)).isoformat()


class SplitEventIntentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "runtime.db"

    def claim(self, ticker="ABC", split_date=None):
        return se.claim_split_event(ticker, split_date or _future(), database=self.db)

    def test_concurrent_claims_have_one_winner(self):
        results = []
        day = _future()
        se.list_unresolved_events(database=self.db)  # migrate once up front

        def run():
            results.append(se.claim_split_event("ABC", day, "x", database=self.db))

        threads = [threading.Thread(target=run) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results.count("claimed"), 1)
        self.assertEqual(results.count("already_claimed"), 7)

    def test_replay_and_new_date(self):
        day = _future(3)
        self.assertEqual(self.claim("abc", day), "claimed")
        self.assertEqual(self.claim("ABC", day), "already_claimed")
        self.assertEqual(self.claim("ABC", _future(90)), "claimed")

    def test_invalid_dates_fail_closed(self):
        for bad in (None, "", "garbage", "2001-01-01", _future(5000)):
            self.assertEqual(
                se.claim_split_event("ABC", bad, database=self.db), "invalid"
            )
        self.assertEqual(se.claim_split_event("bad ticker!", _future(), database=self.db), "invalid")
        self.assertEqual(se.list_unresolved_events(database=self.db), [])

    def test_active_watch_with_other_date_requires_review(self):
        with connect_runtime_db(self.db) as conn:
            run_migrations(conn)
            conn.execute(
                "INSERT INTO split_monitor(ticker, split_date, status) VALUES ('ABC', ?, 'buying')",
                (_future(2),),
            )
        self.assertEqual(self.claim("ABC", _future(30)), "requires_review")
        self.assertEqual(self.claim("ABC", _future(2)), "already_claimed")

    def test_plan_is_recorded_once_and_unique_order_ids(self):
        day = _future()
        self.assertEqual(self.claim("ABC", day), "claimed")
        keys = ["standard:all not x", "override:x"]
        self.assertTrue(se.record_split_order_plan("ABC", day, keys, database=self.db))
        self.assertFalse(se.record_split_order_plan("ABC", day, keys, database=self.db))
        self.assertTrue(se.mark_split_order_queued("ABC", day, keys[0], "id1", database=self.db))
        self.assertFalse(se.mark_split_order_queued("ABC", day, keys[0], "id2", database=self.db))
        with self.assertRaises(sqlite3.IntegrityError):
            se.mark_split_order_queued("ABC", day, keys[1], "id1", database=self.db)
        event = se.get_split_event("ABC", day, database=self.db)
        self.assertEqual(len(event["orders"]), 2)

    def test_reconciliation_listing_and_resolution(self):
        day = _future()
        self.claim("ABC", day)
        se.mark_split_event_needs_reconciliation("ABC", day, "boom", database=self.db)
        self.assertEqual(self.claim("ABC", day), "already_claimed")
        self.assertEqual(se.list_unresolved_events(database=self.db)[0]["state"], "needs_reconciliation")
        self.assertTrue(se.resolve_split_event("ABC", day, database=self.db))
        self.assertEqual(se.list_unresolved_events(database=self.db), [])

    def test_migration_from_v9_preserves_rows_and_is_idempotent(self):
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA foreign_keys = ON")
        from rsassistant.persistence import schema

        for v in range(1, 10):
            schema.MIGRATIONS[v](conn)
            conn.execute(f"PRAGMA user_version = {v}")
            conn.commit()
        conn.execute("INSERT INTO split_monitor(ticker, split_date, status) VALUES ('KEEP','2026-12-01','selling')")
        conn.execute("INSERT INTO split_monitor_accounts(ticker, account_name, bought, sold) VALUES ('KEEP','A',1,0)")
        conn.commit()
        self.assertEqual(run_migrations(conn), LATEST_SCHEMA_VERSION)
        self.assertEqual(run_migrations(conn), LATEST_SCHEMA_VERSION)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM split_monitor_accounts").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM split_event_intents").fetchone()[0], 0)
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
