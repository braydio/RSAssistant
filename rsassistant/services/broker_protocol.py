"""Versioned, typed request/response contract between RSAssistant and a broker worker.

Transport-agnostic: messages are JSON objects. A broker worker never receives a
database handle; everything it needs is in the request. Submit/cancel require an
idempotency key, and the exchange order id is a separate field from the local
intent/correlation ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024


class Operation(str, Enum):
    LIST_ACCOUNTS = "list_accounts"
    POSITIONS = "positions"
    GET_ORDER = "get_order"
    ACTIVITIES = "activities"
    SUBMIT_ORDER = "submit_order"
    CANCEL_ORDER = "cancel_order"
    HEALTH = "health"


MUTATING = {Operation.SUBMIT_ORDER, Operation.CANCEL_ORDER}


class ErrorClass(str, Enum):
    PROTOCOL = "protocol_error"
    VERSION = "version_mismatch"
    TOO_LARGE = "payload_too_large"
    UNSUPPORTED = "unsupported_capability"
    UNAUTHORIZED = "unauthorized"
    SUBMISSION_DISABLED = "submission_disabled"
    BROKER = "broker_error"
    TIMEOUT = "timeout"
    UNKNOWN_OUTCOME = "unknown_outcome"


class ProtocolError(Exception):
    def __init__(self, error_class: ErrorClass, message: str):
        super().__init__(message)
        self.error_class = error_class


@dataclass
class Request:
    op: Operation
    correlation_id: str
    params: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    version: int = PROTOCOL_VERSION

    def to_json(self) -> bytes:
        return json.dumps({
            "version": self.version, "op": self.op.value,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key, "params": self.params,
        }).encode()


@dataclass
class Response:
    correlation_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error_class: ErrorClass | None = None
    message: str = ""
    version: int = PROTOCOL_VERSION

    def to_json(self) -> bytes:
        return json.dumps({
            "version": self.version, "correlation_id": self.correlation_id,
            "ok": self.ok, "result": self.result,
            "error_class": self.error_class.value if self.error_class else None,
            "message": self.message,
        }).encode()

    @classmethod
    def from_json(cls, raw: bytes) -> "Response":
        data = _load(raw)
        ec = data.get("error_class")
        return cls(
            correlation_id=str(data.get("correlation_id", "")),
            ok=bool(data.get("ok")), result=data.get("result"),
            error_class=ErrorClass(ec) if ec else None,
            message=str(data.get("message", "")), version=int(data.get("version", 0)),
        )


def _load(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError(ErrorClass.TOO_LARGE, "message exceeds size limit")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ProtocolError(ErrorClass.PROTOCOL, "invalid JSON") from exc
    if not isinstance(data, dict):
        raise ProtocolError(ErrorClass.PROTOCOL, "message must be an object")
    return data


def parse_request(raw: bytes) -> Request:
    data = _load(raw)
    if data.get("version") != PROTOCOL_VERSION:
        raise ProtocolError(ErrorClass.VERSION, f"expected protocol {PROTOCOL_VERSION}")
    try:
        op = Operation(data.get("op"))
    except ValueError as exc:
        raise ProtocolError(ErrorClass.UNSUPPORTED, "unknown operation") from exc
    correlation_id = data.get("correlation_id")
    if not isinstance(correlation_id, str) or not correlation_id:
        raise ProtocolError(ErrorClass.PROTOCOL, "correlation_id required")
    key = data.get("idempotency_key")
    if op in MUTATING and not (isinstance(key, str) and key):
        raise ProtocolError(ErrorClass.PROTOCOL, "idempotency_key required for mutating ops")
    params = data.get("params") or {}
    if not isinstance(params, dict):
        raise ProtocolError(ErrorClass.PROTOCOL, "params must be an object")
    return Request(op=op, correlation_id=correlation_id, params=params,
                   idempotency_key=key, version=PROTOCOL_VERSION)


class BrokerAdapter(Protocol):
    """Capabilities a broker adapter exposes; absent ones raise NotImplementedError."""

    capabilities: frozenset[Operation]

    def handle(self, request: Request) -> dict[str, Any]: ...


class MockAdapter:
    """In-memory adapter for shadow runs and tests. Records submissions."""

    capabilities = frozenset({
        Operation.LIST_ACCOUNTS, Operation.POSITIONS, Operation.HEALTH,
        Operation.SUBMIT_ORDER, Operation.GET_ORDER,
    })

    def __init__(self, positions: dict[str, list[dict]] | None = None):
        self._positions = positions or {}
        self.submitted: list[dict[str, Any]] = []

    def handle(self, request: Request) -> dict[str, Any]:
        if request.op is Operation.LIST_ACCOUNTS:
            return {"accounts": sorted(self._positions)}
        if request.op is Operation.POSITIONS:
            return {"positions": self._positions.get(request.params.get("account", ""), [])}
        if request.op is Operation.HEALTH:
            return {"status": "healthy", "incidents": []}
        if request.op is Operation.SUBMIT_ORDER:
            self.submitted.append(dict(request.params))
            return {"exchange_order_id": f"mock-{len(self.submitted)}", "state": "accepted"}
        if request.op is Operation.GET_ORDER:
            return {"state": "unknown"}
        raise NotImplementedError(request.op.value)
