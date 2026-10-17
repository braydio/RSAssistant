import json
import tempfile
import unittest
from pathlib import Path

from rsassistant.integrations.brokers.fidelity import errors
from rsassistant.integrations.brokers.fidelity.adapter import FidelitySnapshotAdapter, compare_positions
from rsassistant.services.broker_health import classify_error
from rsassistant.services.broker_protocol import ErrorClass, Operation, Request, Response
from rsassistant.workers.broker_bridge import BrokerWorker


def r(op, **p):
    return Request(op=op, correlation_id="c", params=p, idempotency_key="k" if op is Operation.SUBMIT_ORDER else None)


class FidelityAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "h.json"
        self.path.write_text(json.dumps([
            {"broker": "Fidelity", "group": "1", "account": "123456789", "ticker": "aaa", "quantity": 2},
            {"broker": "Fidelity", "group": "1", "account": "123456789", "ticker": "BBB", "quantity": 1.5},
            {"broker": "Fennel", "group": "1", "account": "9999", "ticker": "ZZZ", "quantity": 1},
        ]))
        self.worker = BrokerWorker(FidelitySnapshotAdapter(self.path), allow_submit=True)

    def call(self, req):
        return Response.from_json(self.worker.process(req.to_json()))

    def test_accounts_positions_health_only_fidelity(self):
        self.assertEqual(self.call(r(Operation.LIST_ACCOUNTS)).result["accounts"],
                         [{"group": "1", "account": "123456789"}])
        pos = self.call(r(Operation.POSITIONS)).result["positions"]
        self.assertEqual([p["ticker"] for p in pos], ["AAA", "BBB"])
        self.assertEqual(self.call(r(Operation.HEALTH)).result["mode"], "snapshot_shadow")

    def test_submit_and_order_status_explicitly_unsupported_even_when_submission_enabled(self):
        for op in (Operation.SUBMIT_ORDER, Operation.GET_ORDER, Operation.ACTIVITIES):
            self.assertEqual(self.call(r(op)).error_class, ErrorClass.UNSUPPORTED, op)

    def test_compare_redacts_accounts_and_finds_diffs(self):
        a = [{"group": "1", "account": "123456789", "ticker": "AAA", "quantity": 2},
             {"group": "1", "account": "123456789", "ticker": "BBB", "quantity": 1}]
        b = [{"group": "1", "account": "123456789", "ticker": "AAA", "quantity": 3},
             {"group": "1", "account": "123456789", "ticker": "CCC", "quantity": 1}]
        d = compare_positions(a, b)
        self.assertFalse(d["match"])
        self.assertEqual(d["quantity_mismatch"][0]["account"], "*****6789")
        self.assertNotIn("123456789", json.dumps(d))
        self.assertTrue(compare_positions(a, list(a))["match"])

    def test_error_classes_align_with_health_classifier(self):
        self.assertEqual(errors.UnknownOrderOutcome.error_class,
                         classify_error("order button clicked but confirmation not detected").error_class)
        self.assertEqual(errors.BrowserLaunchError.error_class,
                         classify_error("Failed to connect to browser").error_class)


if __name__ == "__main__":
    unittest.main()
