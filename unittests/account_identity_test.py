import tempfile
import unittest
from pathlib import Path

from rsassistant.persistence import account_identity as ai
from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations


def row(i, broker, group, number, nick=None):
    return dict(account_id=i, broker=broker, broker_number=group,
                account_number=number, account_nickname=nick)


class NormalizationTest(unittest.TestCase):
    def test_labels_and_masks(self):
        self.assertEqual(ai.normalize_group("Fidelity 1"), "1")
        self.assertEqual(ai.normalize_group("CHASE 1"), "1")
        self.assertEqual(ai.normalize_broker("Wells Fargo"), "wellsfargo")
        self.assertEqual(ai.account_forms("123456789"), ("6789", "123456789"))
        self.assertEqual(ai.account_forms("xxxxxxxxxxxxxxxx7d15"), ("7d15", None))
        self.assertEqual(ai.account_forms("80"), ("0080", None))


class PlanTest(unittest.TestCase):
    def test_casing_and_labels_merge_but_stay_unverified_on_last4(self):
        plan = ai.build_plan([
            row(1, "FIDELITY", "1", "6699"),
            row(2, "Fidelity", "Fidelity 1", "6699"),
        ])
        self.assertEqual(len(plan.canonicals), 1)
        self.assertEqual({m["verified"] for m in plan.mappings.values()}, {0})

    def test_same_full_number_is_verified(self):
        plan = ai.build_plan([
            row(1, "Fidelity", "1", "123456789"),
            row(2, "FIDELITY", "Fidelity 1", "123456789"),
        ])
        self.assertEqual(len(plan.canonicals), 1)
        self.assertEqual({m["verified"] for m in plan.mappings.values()}, {1})

    def test_last4_collision_across_groups_not_merged(self):
        plan = ai.build_plan([row(1, "Fidelity", "1", "7968"), row(2, "Fidelity", "2", "7968")])
        self.assertEqual(len(plan.canonicals), 2)

    def test_conflicting_full_numbers_are_ambiguous_not_merged(self):
        plan = ai.build_plan([
            row(1, "Fidelity", "1", "111116699"),
            row(2, "Fidelity", "1", "222226699"),
            row(3, "Fidelity", "1", "6699"),
        ])
        self.assertEqual(len(plan.canonicals), 3)
        self.assertEqual({m["match_basis"] for m in plan.mappings.values()}, {"ambiguous"})


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "t.db")
        conn = connect_runtime_db(self.db)
        run_migrations(conn)
        conn.executemany(
            "INSERT INTO Accounts(account_id,broker,account_number,broker_number) VALUES (?,?,?,?)",
            [(1, "Fidelity", "6699", "1"), (2, "FIDELITY", "6699", "Fidelity 1"),
             (3, "Fidelity", "1111", "1"), (4, "B", "1", "1"), (5, "Chase", "9999", "1")],
        )
        conn.execute(
            "INSERT INTO holdings_current(account_id,ticker,quantity,price,position_value,observed_at,source)"
            " VALUES (1,'AAA',1,1,1,'t','s')"
        )
        conn.execute(
            "INSERT INTO OrderHistory(order_id,account_id,broker,broker_name,account_number,ticker,date,action,quantity,price,total_value)"
            " VALUES ('o',3,'Fidelity','Fidelity','1111','AAA','d','buy',1,1,1)"
        )
        conn.commit()
        conn.close()

    def test_refresh_is_idempotent_non_destructive_and_classifies(self):
        first = ai.refresh_canonical_map(database=self.db)
        self.assertEqual(first, {"legacy_accounts": 5, "canonical_accounts": 4})
        ai.refresh_canonical_map(database=self.db)
        conn = connect_runtime_db(self.db)
        self.assertEqual(conn.execute("SELECT count(*) FROM Accounts").fetchone()[0], 5)
        self.assertEqual(conn.execute("SELECT count(*) FROM account_canonical_map").fetchone()[0], 5)
        conn.close()
        report = {(r["broker"], r["status"]): r for r in ai.mapping_report(database=self.db)}
        self.assertEqual(report[("fidelity", "active")]["legacy_rows"], 2)
        self.assertEqual(report[("fidelity", "historical")]["canonical"], 1)
        self.assertIn(("b", "fixture"), report)
        self.assertEqual(report[("chase", "dormant")]["canonical"], 1)


if __name__ == "__main__":
    unittest.main()
