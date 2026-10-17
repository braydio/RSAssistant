import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from rsassistant.persistence import order_intents as oi
from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils import parsing_utils


class OrderIntentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "t.db")
        conn = connect_runtime_db(self.db)
        run_migrations(conn)
        conn.execute(
            "INSERT INTO rsa_order_send_log(send_id,sent_at,command,channel_id,ticker,"
            "action,quantity,broker) VALUES (1,'2026-10-15T17:23:18+00:00',"
            "'!rsa buy 1 FRGT all false','c','FRGT','buy',1,'all'),"
            "(2,'2026-10-15T18:00:00+00:00','!rsa buy 1 ZZZ all false','c','ZZZ','buy',1,'all')"
        )
        conn.commit()
        conn.close()

    def _intent(self, send_id=1, **kw):
        return oi.create_intent_for_send(
            send_id, ticker="FRGT", action="buy", quantity=1, broker="all",
            created_at=datetime.now(timezone.utc).isoformat(), database=self.db, **kw
        )

    def _state(self, intent_id):
        conn = connect_runtime_db(self.db)
        try:
            return conn.execute(
                "SELECT state, evidence_grade FROM order_intents WHERE intent_id=?",
                (intent_id,),
            ).fetchone()
        finally:
            conn.close()

    def test_intent_idempotent_and_only_dispatched(self):
        a, b = self._intent(), self._intent()
        self.assertEqual(a, b)
        self.assertEqual(tuple(self._state(a)), ("dispatched", "discord_send_only"))

    def test_confirmation_text_is_accepted_not_filled(self):
        iid = self._intent()
        rid = oi.record_receipt(
            outcome="accepted_reported", evidence="Fidelity 1 account 1234: buy 1 shares of FRGT",
            discord_message_id=42, broker="Fidelity", ticker="FRGT", action="buy",
            database=self.db,
        )
        self.assertIsNotNone(rid)
        self.assertEqual(tuple(self._state(iid)), ("broker_accepted", "legacy_text"))
        conn = connect_runtime_db(self.db)
        self.assertEqual(conn.execute("SELECT count(*) FROM execution_fills").fetchone()[0], 0)
        conn.close()

    def test_replayed_message_is_noop(self):
        self._intent()
        kw = dict(outcome="accepted_reported", evidence="x", discord_message_id=7,
                  ticker="FRGT", action="buy", database=self.db)
        self.assertIsNotNone(oi.record_receipt(**kw))
        self.assertIsNone(oi.record_receipt(**kw))

    def test_ambiguous_candidates_stay_unlinked(self):
        a = self._intent(1)
        conn = connect_runtime_db(self.db)
        conn.execute("INSERT INTO rsa_order_send_log(send_id,sent_at,command,channel_id,ticker,action,quantity,broker) VALUES (3,'x','c','c','FRGT','buy',1,'all')")
        conn.commit(); conn.close()
        self._intent(3)
        oi.record_receipt(outcome="accepted_reported", evidence="x", discord_message_id=1,
                          ticker="FRGT", action="buy", database=self.db)
        self.assertEqual(tuple(self._state(a)), ("dispatched", "discord_send_only"))

    def test_old_intent_outside_window_not_linked(self):
        old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        iid = oi.create_intent_for_send(1, ticker="FRGT", action="buy", quantity=1,
                                        broker="all", created_at=old, database=self.db)
        oi.record_receipt(outcome="accepted_reported", evidence="x", discord_message_id=5,
                          ticker="FRGT", action="buy", database=self.db)
        self.assertEqual(self._state(iid)[0], "dispatched")

    def test_backfill_marks_unknown_needs_review_and_report(self):
        self.assertEqual(oi.backfill_from_send_log(database=self.db), 2)
        self.assertEqual(oi.backfill_from_send_log(database=self.db), 0)
        report = oi.unverified_report(database=self.db)
        self.assertEqual(report[0]["broker"], "all")
        self.assertEqual(report[0]["state"], "unknown")
        self.assertEqual(report[0]["intents"], 2)

    def test_parse_records_receipt_without_changing_history_path(self):
        msg = "Fidelity 1 account xxxxx1234: buy 1 shares of FRGT"
        with patch("utils.parsing_utils.order_intents.record_receipt") as rec, \
             patch("utils.parsing_utils.get_last_stock_price", return_value=None), \
             patch("utils.parsing_utils.handoff_order_data") as hand:
            parsing_utils.parse_order_message(msg, 99)
        kw = rec.call_args.kwargs
        self.assertEqual(kw["outcome"], "accepted_reported")
        self.assertEqual(kw["discord_message_id"], 99)
        self.assertEqual(kw["ticker"], "FRGT")
        hand.assert_called_once()

    def test_receipt_failure_never_breaks_parsing(self):
        msg = "Fidelity 1 account xxxxx1234: buy 1 shares of FRGT"
        with patch("utils.parsing_utils.order_intents.record_receipt", side_effect=RuntimeError("x")), \
             patch("utils.parsing_utils.get_last_stock_price", return_value=5.0), \
             patch("utils.parsing_utils.handoff_order_data") as hand:
            parsing_utils.parse_order_message(msg, 1)
        hand.assert_called_once()


if __name__ == "__main__":
    unittest.main()
