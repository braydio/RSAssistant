"""Write-ahead dispatch of an order intent through the typed broker bridge.

Disabled unless ``RSA_BROKER_BRIDGE_ENABLED=true`` -- the production path is
still the legacy Discord ``!rsa`` flow. This function never retries: if the
outcome of a submit is unknown the intent is parked as ``unknown`` +
``needs_review`` for reconciliation.
"""

from __future__ import annotations

import os
import uuid

from rsassistant.persistence import order_intents
from rsassistant.services.broker_protocol import ErrorClass, Operation, Request


def bridge_enabled() -> bool:
    return os.getenv("RSA_BROKER_BRIDGE_ENABLED", "false").strip().lower() == "true"


def dispatch_intent(client, intent_id: str, *, ticker: str, action: str,
                    quantity: float, account: str, database=None) -> str:
    """Return the resulting intent state; never raises for transport errors."""
    if not bridge_enabled():
        raise RuntimeError("broker bridge disabled (RSA_BROKER_BRIDGE_ENABLED != true)")
    if not order_intents.claim_for_dispatch(intent_id, database=database):
        return "already_claimed"  # a second caller can never send a second order
    resp = client.call(Request(
        op=Operation.SUBMIT_ORDER,
        correlation_id=str(uuid.uuid4()),
        idempotency_key=intent_id,
        params={"ticker": ticker, "action": action, "quantity": quantity,
                "account": account},
    ))
    if resp.ok:
        order_intents.set_intent_state(intent_id, "broker_accepted", database=database)
        return "broker_accepted"
    if resp.error_class in (ErrorClass.UNKNOWN_OUTCOME, ErrorClass.TIMEOUT):
        order_intents.set_intent_state(intent_id, "unknown", needs_review=True, database=database)
        return "unknown"
    order_intents.set_intent_state(intent_id, "rejected", needs_review=True, database=database)
    return "rejected"
