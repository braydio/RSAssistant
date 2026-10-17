# TP-20261016-004: Recover order acknowledgement and broker fill provenance

**Packet ID:** TP-20261016-004  
**Status:** Complete
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261016-004-order-receipts-and-fill-reconciliation.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-003  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-004 is #4; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Recover order acknowledgement and broker fill provenance. Preserve current production behavior unless the scoped acceptance criteria and required gates have been satisfied. Any live trading cutover is outside this packet unless explicitly specified.

## Current evidence and source boundary
FRGT 2026-10-15 command reached Discord but autoreplies were filtered by unset TRUSTED_AUTORSA_BOT_ID; yfinance failure discarded orders. 151 sends after 2026-08-05 without new OrderHistory; Fidelity has ~1100 ambiguous confirmation logs.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These facts are not equivalent. Do not implement on stale assumptions.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: verify 83a6b00 trusted bot + price 0 fix landed; sample broker source/activity records for FRGT and Fidelity ambiguous orders. Missing confirmation never permits replay.**

The implementer must mark this packet `In Progress` in `TRACKER.md` and `INDEX.md` **only after** reviewing dependency completion summaries and confirming the named files/symbols on the *then-current* canonical main. If drift changes SQL/IPC/trading semantics, refresh packet and record rationale before execution. No executing `Draft` or `Blocked`.

## Exact target files and symbols
- `utils/order_exec.py`
- `utils/order_dispatcher.py`
- `utils/order_send_log_manager.py`
- `rsassistant/persistence/orders.py`
- `rsassistant/persistence/schema.py`
- `rsassistant/bot/handlers/on_message.py`
- `utils/parsing_utils.py`
- `unittests/order_history_repository_test.py`
- `unittests/order_dispatcher_test.py`
- `unittests/order_send_commands_test.py`

## Required implementation, in order
1. Create additive order_intents, broker_order_receipts and execution_fills tables with durable unique idempotency keys; preserve current OrderHistory/rsa_order_send_log rows and foreign-key schema. Intent states: planned, queued, dispatched, broker_accepted, partially_filled, filled, rejected, cancelled, unknown, reconciled.
2. Correlate outbound message, auto-rsa response and target login/account using durable intent ID where supported; legacy text parser records evidence snippets/source message IDs, never pretends to be broker fills. Split queued/sent/acknowledged/filled counters.
3. Modify confirmation ingestion so quote lookup is enrichment only. Broker-filled price may be NULL if absent; do not synthesize fill at $0 or use market quote as execution price. Reconcile price from broker activity later.
4. Build read-only legacy backfill from send logs and OrderHistory into intents with evidence_grade and no generated fills; unidentified or ambiguous commands remain needs_review.
5. Ensure unknown broker outcomes are not retried automatically, preserve per-event claim behavior from local TP-20261013-001; add operator report of unverified executions grouped by broker/account.

### Invariants / validation boundaries
- No brokerage command may be presumed filled from Discord send alone; preserve reported status and provenance.
- Do not resurrect auto-buys for old events when replaying stale or missing evidence; preserve the split-event durable claim from TP-20261013-001.
- New state belongs to canonical SQLite; legacy JSON/CSV may be fixtures or transitional input only.
- Tests must use temporary databases and mock broker transport. No live order, no credential dump, no production DB fixtures.
- Preserve original open split watches and all unresolved position/order evidence, including BTOC/KNDI/FRGT/OBAI if still outstanding at execution time.
- Include one reversible data migration strategy when schema changes and a downgrade/rollback note in the completion summary.

## Focused and full validation
- `python -m unittest unittests.order_history_repository_test unittests.order_dispatcher_test unittests.order_send_commands_test`
- `synthetic conflicting/replayed Discord messages, quote failures, broker fill response, partial fill and unknown outcome`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Production acceptance requires an operator-reviewed read-only parity report; record exact timestamps, source versions and unknowns.

## Acceptance criteria
- [ ] All outbound intents have durable source and status
- [ ] No order is considered filled from a Discord send or generic success string alone
- [ ] One ambiguous retry produces zero new broker orders
- [ ] Can trace historical FRGT as sent but unverified, without inventing fills
- [ ] No regression to event idempotency, existing broker order queues or account historical data.
- [ ] Completion summary describes coverage, schema/backfill, observed runtime differences and any remaining human review.

## Explicit non-goals
No live backtrades, no forced broker login, no guessed cost basis, no movement of capital.

## Handoff / completion report
On verified completion move exactly this canonical file from `active/` to `completed/`, update `INDEX.md` and `TRACKER.md` atomically, and write `docs/task-packets/summaries/TP-20261016-004-SUMMARY.md` (Outcome, Validation, Process Feedback, Next Handoff). State next packet TP-20261016-005 and whether a fresh planning review is required; never claim production parity from mocks only.
