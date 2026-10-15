"""Single-task dispatcher for scheduled orders.

Replaces one sleeping asyncio task per order with one dispatcher task that
sleeps until the earliest due order. Durable state lives in the SQLite
``scheduled_orders`` table; this module only keeps the in-memory context
(channel/bot) needed to send, keyed by order id (so re-registering the same id
can never schedule it twice).

Transitions: ``pending -> dispatching`` (atomic claim) ``-> deleted`` on a
confirmed send, ``-> pending`` on a clean failure (``send`` returned False) or
``-> needs_review`` when the outcome is ambiguous (``send`` raised). Ambiguous
orders are never re-sent automatically.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from utils.market_calendar import MARKET_TZ, is_market_open_at, next_market_open
from utils.order_queue_manager import (
    CLAIM_CLAIMED,
    claim_order,
    get_scheduled_states,
    mark_order_needs_review,
    release_order,
    remove_order,
)

logger = logging.getLogger(__name__)

MAX_SLEEP_SECONDS = 3600.0


@dataclass
class PendingOrder:
    order_id: str
    action: str
    ticker: str
    quantity: float
    broker: str
    ctx: Any
    bot: Any = None


def effective_execution_time(scheduled_at: datetime, now: datetime) -> datetime:
    """Apply the legacy rule: never earlier than now, and only at market open."""

    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=MARKET_TZ)
    reference = scheduled_at if scheduled_at > now else now
    if not is_market_open_at(reference):
        return next_market_open(reference)
    return scheduled_at


class OrderDispatcher:
    def __init__(
        self,
        send: Callable[[PendingOrder], Awaitable[bool]],
        on_sent: Callable[[PendingOrder], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._send = send
        self._on_sent = on_sent
        self._clock = clock or (lambda: datetime.now(MARKET_TZ))
        self._pending: dict[str, PendingOrder] = {}
        self._task: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None

    # -- registration -------------------------------------------------
    def register(self, order: PendingOrder) -> None:
        """Register (or replace) an order and make sure the dispatcher runs."""

        self._pending[order.order_id] = order
        self.ensure_running()
        if self._wake is not None:
            self._wake.set()  # recompute the earliest due time

    def ensure_running(self) -> None:
        if self._task is None or self._task.done():
            self._wake = asyncio.Event()
            self._task = asyncio.get_running_loop().create_task(
                self._run(), name="order-dispatcher"
            )

    def discard(self, order_id: str) -> None:
        self._pending.pop(order_id, None)

    @property
    def registered_count(self) -> int:
        return len(self._pending)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # -- scanning -----------------------------------------------------
    def scan(self) -> tuple[list[PendingOrder], float | None]:
        """Return ``(due_orders, seconds_until_next)`` and prune cancelled ones."""

        states = get_scheduled_states(self._pending)
        now = self._clock()
        due: list[PendingOrder] = []
        soonest: float | None = None
        for order_id in list(self._pending):
            row = states.get(order_id)
            if row is None or row[1] != "pending":
                # Removed/cancelled, claimed elsewhere, or parked for review.
                self._pending.pop(order_id, None)
                continue
            try:
                scheduled = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                logger.error("Order %s has unparseable time %r; dropping.", order_id, row[0])
                self._pending.pop(order_id, None)
                continue
            wait = (effective_execution_time(scheduled, now) - now).total_seconds()
            if wait <= 0:
                due.append(self._pending[order_id])
            elif soonest is None or wait < soonest:
                soonest = wait
        return due, soonest

    # -- dispatch -----------------------------------------------------
    async def dispatch(self, order: PendingOrder) -> bool:
        """Claim and send one order. Returns True only for a confirmed send."""

        self._pending.pop(order.order_id, None)
        if claim_order(order.order_id) != CLAIM_CLAIMED:
            logger.info("Order %s not claimable; skipping send.", order.order_id)
            return False
        try:
            sent = await self._send(order)
        except asyncio.CancelledError:
            mark_order_needs_review(order.order_id, "cancelled while dispatching")
            raise
        except Exception as exc:
            mark_order_needs_review(order.order_id, f"{type(exc).__name__} during send")
            logger.error(
                "Order %s send raised %s; parked as needs_review (not re-sent).",
                order.order_id,
                type(exc).__name__,
            )
            return False
        if not sent:
            release_order(order.order_id, "send reported failure")
            logger.warning("Order %s remains queued because Discord send failed.", order.order_id)
            return False
        if self._on_sent:
            self._on_sent(order)
        remove_order(order.order_id)
        return True

    async def _run(self) -> None:
        while True:
            due, wait = self.scan()
            for order in due:
                await self.dispatch(order)
            if due:
                continue  # rescan: sends take time and the queue may have changed
            if not self._pending:
                return  # idle: no task at all until the next registration
            assert self._wake is not None
            self._wake.clear()
            timeout = MAX_SLEEP_SECONDS if wait is None else min(wait, MAX_SLEEP_SECONDS)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
