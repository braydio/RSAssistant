import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import holdings_reconcile as hr  # noqa: E402


class HoldingsReconcileTest(unittest.TestCase):
    def test_flat_and_nested_snapshots_and_db_parity(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            flat = d / "flat.json"
            flat.write_text(json.dumps([
                {"broker": "Fidelity", "group": "1", "account": "9", "ticker": "AAA"},
                {"broker": "Fidelity", "group": "1", "account": "9", "ticker": "BBB"},
            ]))
            nested = d / "nested.json"
            nested.write_text(json.dumps({"brokers": {"Fidelity": {"1": {"9": {
                "AAA": {"quantity": 1}, "BBB": {"quantity": 1}, "_account_total": 3}}}}}))
            expect = {"fidelity": {"accounts": 1, "positions": 2}}
            self.assertEqual(hr.snapshot_summary(flat), expect)
            self.assertEqual(hr.snapshot_summary(nested), expect)

            db = d / "t.db"
            conn = sqlite3.connect(db)
            conn.executescript("""
                CREATE TABLE Accounts(account_id INTEGER PRIMARY KEY, broker TEXT);
                CREATE TABLE holdings_current(account_id INT, ticker TEXT, observed_at TEXT);
                INSERT INTO Accounts VALUES (1,'Fidelity');
                INSERT INTO holdings_current VALUES (1,'AAA','t'),(1,'BBB','t');
            """)
            conn.commit(); conn.close()
            report = hr.build_report(db, flat)
            row = report["brokers"][0]
            self.assertTrue(row["accounts_match"] and row["positions_match"])
            self.assertEqual(hr.main(["--db", str(db), "--snapshot", str(flat)]), 0)


if __name__ == "__main__":
    unittest.main()
