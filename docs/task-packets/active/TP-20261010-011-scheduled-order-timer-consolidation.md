# TP-20261010-011: Consolidate Long-Sleep Order Tasks without Changing Execution Semantics

**Packet ID:** TP-20261010-011  
**Status:** Draft  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-011-scheduled-order-timer-consolidation.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** TP-20261003-004 (dependency refresh required)  
**Priority:** High  
**Authoring chat:** not-recorded  

## Objective

Reduce consolidate long-sleep order tasks without changing execution semantics overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `rsassistant/bot/tasks.py`
- `utils/order_exec.py`
- `utils/order_queue_manager.py`
- `rsassistant/bot/cogs/orders.py`
- `unittests/order_queue_tasks_test.py`
- `unittests/order_send_commands_test.py`

## Confirmed current behavior

`reschedule_queued_orders()` and `reschedule_past_due_orders()` each schedule `schedule_and_execute(...)` tasks; `schedule_and_execute()` can sleep until execution time, retaining one asyncio task per order. Two rescheduling entrypoints can schedule the same queue rows if no in-memory claimed-order guard. TP-20261003-004 is already specifying typed SQLite `scheduled_orders`; do not implement another competing queue.

## Required changes and implementation order

1. Once TP-004 lands, consume its authoritative SQLite scheduled-orders API to schedule **one** dispatcher wakeup for the earliest due order or use a bounded due-order query loop, rather than one multi-day sleep per order. Recalculate on add/update/cancel and startup.
2. Persist state transitions `pending -> dispatching -> sent/failed` via transactionally claimed due orders; retain broker/action/ticker/quantity and current next-market-open semantics. Preserve audit and retry policy; if schema requires expansion, append migration in existing TP-004 lineage only after dependency refresh.
3. Avoid concurrent dispatcher instances for same order in one process; on restart recover stale claimed orders conservatively. Network send and durable completion are non-atomic: document the inherent ambiguity and favor manual reconciliation rather than unsafe automatic duplicate re-sends.
4. Maintain `schedule_and_execute` API compatibility as an adapter for callers; keep stock-market calendar/DST and no-order-on-market-closed invariants.
5. **Refresh gate**: check TP-004 implementation/summary and actual current main, update precise SQL statements and migration version in this packet before Ready.

## Focused tests and validation

Use fake clock for next-due, 100 pending orders with constant task count, restart recovery, duplicate scheduler prevention, failed Discord send, market holidays/DST, cancellation, and pending->dispatching claim contention. `python -m pytest -q unittests/order_queue_tasks_test.py unittests/order_send_commands_test.py`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] At most a constant number of dispatcher tasks regardless of queued orders and no regression in order safety, timing, persistence, or sent-order auditing.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-011-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No blind exactly-once guarantee over Discord, no trade execution strategy rewrite, and no schema change ahead of TP-004.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
