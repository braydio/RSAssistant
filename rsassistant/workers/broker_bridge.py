"""Broker worker: dispatches typed requests to an adapter over a Unix socket.

* No database access -- the worker only sees request params.
* Socket is created mode 0600 in a 0700 directory and each connection's peer
  uid is checked (SO_PEERCRED) against the worker's own uid.
* Mutating operations are rejected unless ``allow_submit`` is set; the default
  is read-only shadow mode.
* Replayed idempotency keys return the first response and never re-invoke the
  adapter, so a client retry cannot create a second broker order.
"""

from __future__ import annotations

import os
import socket
import struct
import threading
from pathlib import Path

from rsassistant.services.broker_protocol import (
    MAX_MESSAGE_BYTES, MUTATING, BrokerAdapter, ErrorClass, ProtocolError,
    Request, Response, parse_request,
)


class BrokerWorker:
    def __init__(self, adapter: BrokerAdapter, *, allow_submit: bool = False):
        self.adapter = adapter
        self.allow_submit = allow_submit
        self._seen: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def process(self, raw: bytes) -> bytes:
        """Pure request->response; never raises."""
        try:
            req = parse_request(raw)
        except ProtocolError as exc:
            return Response("", False, error_class=exc.error_class, message=str(exc)).to_json()
        return self._dispatch(req)

    def _dispatch(self, req: Request) -> bytes:
        if req.op not in self.adapter.capabilities:
            return Response(req.correlation_id, False, error_class=ErrorClass.UNSUPPORTED,
                            message=f"{req.op.value} not supported").to_json()
        if req.op in MUTATING:
            if not self.allow_submit:
                return Response(req.correlation_id, False,
                                error_class=ErrorClass.SUBMISSION_DISABLED,
                                message="worker is in read-only shadow mode").to_json()
            with self._lock:
                cached = self._seen.get(req.idempotency_key or "")
                if cached is not None:
                    return cached
                out = self._call(req)
                self._seen[req.idempotency_key or ""] = out
                return out
        return self._call(req)

    def _call(self, req: Request) -> bytes:
        try:
            result = self.adapter.handle(req)
        except NotImplementedError:
            return Response(req.correlation_id, False, error_class=ErrorClass.UNSUPPORTED).to_json()
        except Exception as exc:  # adapter failure: typed, never a crash
            return Response(req.correlation_id, False, error_class=ErrorClass.BROKER,
                            message=type(exc).__name__).to_json()
        return Response(req.correlation_id, True, result=result).to_json()


def _peer_uid(conn: socket.socket) -> int:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


class UnixSocketServer:
    def __init__(self, worker: BrokerWorker, path: str | Path):
        self.worker = worker
        self.path = Path(path)
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self.path.exists():
            self.path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(self.path))
        os.chmod(self.path, 0o600)
        sock.listen(8)
        sock.settimeout(0.2)
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._sock:
            self._sock.close()
        if self.path.exists():
            self.path.unlink()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            with conn:
                conn.settimeout(5)
                try:
                    if _peer_uid(conn) != os.getuid():
                        out = Response("", False, error_class=ErrorClass.UNAUTHORIZED).to_json()
                    else:
                        out = self.worker.process(_recv_line(conn))
                    conn.sendall(out + b"\n")
                except (OSError, ProtocolError):
                    pass


def _recv_line(conn: socket.socket) -> bytes:
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > MAX_MESSAGE_BYTES:
            raise ProtocolError(ErrorClass.TOO_LARGE, "message exceeds size limit")
    return buf.strip()


class BridgeClient:
    """Client side. A transport failure is reported as an *unknown* outcome."""

    def __init__(self, path: str | Path, timeout: float = 5.0):
        self.path = str(path)
        self.timeout = timeout

    def call(self, req: Request) -> Response:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect(self.path)
                s.sendall(req.to_json() + b"\n")
                return Response.from_json(_recv_line(s))
        except socket.timeout:
            et = ErrorClass.UNKNOWN_OUTCOME if req.op in MUTATING else ErrorClass.TIMEOUT
            return Response(req.correlation_id, False, error_class=et, message="timeout")
        except (OSError, ProtocolError):
            et = ErrorClass.UNKNOWN_OUTCOME if req.op in MUTATING else ErrorClass.PROTOCOL
            return Response(req.correlation_id, False, error_class=et, message="transport failure")
