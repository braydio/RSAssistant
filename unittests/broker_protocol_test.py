import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from rsassistant.persistence import order_intents as oi
from rsassistant.services import bridge_dispatch as bd
from rsassistant.services.broker_protocol import (
    MAX_MESSAGE_BYTES, ErrorClass, MockAdapter, Operation, ProtocolError, Request,
    Response, parse_request,
)
from rsassistant.workers.broker_bridge import BridgeClient, BrokerWorker, UnixSocketServer


def req(op, key=None, **params):
    return Request(op=op, correlation_id="c1", params=params, idempotency_key=key)


class ProtocolTest(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(ProtocolError) as e:
            parse_request(b"{bad")
        self.assertEqual(e.exception.error_class, ErrorClass.PROTOCOL)
        bad_version = json.dumps({"version": 99, "op": "health", "correlation_id": "x"}).encode()
        with self.assertRaises(ProtocolError) as e:
            parse_request(bad_version)
        self.assertEqual(e.exception.error_class, ErrorClass.VERSION)
        with self.assertRaises(ProtocolError) as e:
            parse_request(b"x" * (MAX_MESSAGE_BYTES + 1))
        self.assertEqual(e.exception.error_class, ErrorClass.TOO_LARGE)
        with self.assertRaises(ProtocolError):
            parse_request(req(Operation.SUBMIT_ORDER).to_json())  # no idempotency key
        with self.assertRaises(ProtocolError):
            parse_request(json.dumps({"version": 1, "op": "nope", "correlation_id": "x"}).encode())


class WorkerTest(unittest.TestCase):
    def test_read_only_shadow_never_submits(self):
        adapter = MockAdapter({"a1": [{"ticker": "AAA", "quantity": 1}]})
        worker = BrokerWorker(adapter)
        pos = Response.from_json(worker.process(req(Operation.POSITIONS, account="a1").to_json()))
        self.assertTrue(pos.ok)
        self.assertEqual(pos.result["positions"][0]["ticker"], "AAA")
        sub = Response.from_json(worker.process(req(Operation.SUBMIT_ORDER, "k").to_json()))
        self.assertEqual(sub.error_class, ErrorClass.SUBMISSION_DISABLED)
        self.assertEqual(adapter.submitted, [])

    def test_unsupported_capability_is_explicit(self):
        worker = BrokerWorker(MockAdapter())
        r = Response.from_json(worker.process(req(Operation.CANCEL_ORDER, "k").to_json()))
        self.assertEqual(r.error_class, ErrorClass.UNSUPPORTED)

    def test_duplicate_idempotency_key_submits_once(self):
        adapter = MockAdapter()
        worker = BrokerWorker(adapter, allow_submit=True)
        a = worker.process(req(Operation.SUBMIT_ORDER, "same", ticker="X").to_json())
        b = worker.process(req(Operation.SUBMIT_ORDER, "same", ticker="X").to_json())
        self.assertEqual(a, b)
        self.assertEqual(len(adapter.submitted), 1)

    def test_adapter_exception_is_typed(self):
        class Boom(MockAdapter):
            def handle(self, request):
                raise RuntimeError("secret detail")
        r = Response.from_json(BrokerWorker(Boom()).process(req(Operation.HEALTH).to_json()))
        self.assertEqual(r.error_class, ErrorClass.BROKER)
        self.assertNotIn("secret", r.message)


class SocketTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "run" / "w.sock"
        self.adapter = MockAdapter({"a1": []})
        self.server = UnixSocketServer(BrokerWorker(self.adapter), self.path)
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_permissions_and_roundtrip(self):
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(self.path.parent.stat().st_mode & 0o777), "0o700")
        r = BridgeClient(self.path).call(req(Operation.LIST_ACCOUNTS))
        self.assertTrue(r.ok)
        self.assertEqual(r.result["accounts"], ["a1"])

    def test_oversized_payload_rejected(self):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(3)
            s.connect(str(self.path))
            try:
                s.sendall(b"x" * (MAX_MESSAGE_BYTES * 2) + b"\n")
            except OSError:
                pass
            try:
                data = s.recv(65536)
            except OSError:
                data = b""
        self.assertEqual(self.adapter.submitted, [])
        if data:
            self.assertEqual(Response.from_json(data.strip()).error_class, ErrorClass.TOO_LARGE)

    def test_dead_socket_submit_is_unknown_outcome(self):
        r = BridgeClient(self.path.parent / "missing.sock").call(req(Operation.SUBMIT_ORDER, "k"))
        self.assertEqual(r.error_class, ErrorClass.UNKNOWN_OUTCOME)


class DispatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / "t.db")
        self.adapter = MockAdapter()
        self.worker = BrokerWorker(self.adapter, allow_submit=True)

    class _Local:
        def __init__(self, worker, fail=None):
            self.worker, self.fail = worker, fail

        def call(self, request):
            if self.fail:
                return Response(request.correlation_id, False, error_class=self.fail)
            return Response.from_json(self.worker.process(request.to_json()))

    def _intent(self):
        return oi.create_planned_intent(ticker="AAA", action="buy", quantity=1,
                                        broker="fidelity", database=self.db)

    def _state(self, iid):
        from rsassistant.persistence.db import connect_runtime_db
        c = connect_runtime_db(self.db)
        try:
            return c.execute("SELECT state, needs_review FROM order_intents WHERE intent_id=?",
                             (iid,)).fetchone()
        finally:
            c.close()

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RSA_BROKER_BRIDGE_ENABLED", None)
            with self.assertRaises(RuntimeError):
                bd.dispatch_intent(self._Local(self.worker), self._intent(), ticker="AAA",
                                   action="buy", quantity=1, account="a", database=self.db)

    def test_claim_once_and_unknown_outcome_never_retries(self):
        with patch.dict(os.environ, {"RSA_BROKER_BRIDGE_ENABLED": "true"}):
            iid = self._intent()
            kw = dict(ticker="AAA", action="buy", quantity=1, account="a", database=self.db)
            self.assertEqual(bd.dispatch_intent(self._Local(self.worker), iid, **kw), "broker_accepted")
            self.assertEqual(bd.dispatch_intent(self._Local(self.worker), iid, **kw), "already_claimed")
            self.assertEqual(len(self.adapter.submitted), 1)

            lost = self._intent()
            out = bd.dispatch_intent(self._Local(self.worker, fail=ErrorClass.UNKNOWN_OUTCOME), lost, **kw)
            self.assertEqual(out, "unknown")
            self.assertEqual(tuple(self._state(lost)), ("unknown", 1))
            self.assertEqual(bd.dispatch_intent(self._Local(self.worker), lost, **kw), "already_claimed")
            self.assertEqual(len(self.adapter.submitted), 1)

    def test_filled_cannot_be_set_without_broker_activity(self):
        with self.assertRaises(ValueError):
            oi.set_intent_state(self._intent(), "filled", database=self.db)


if __name__ == "__main__":
    unittest.main()
