# TP-20261016-008: Direct typed broker worker bridge and shadow orchestration

**Packet ID:** TP-20261016-008  
**Status:** Draft  
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-008-typed-broker-worker-ipc.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-004, -005, -006 and -007  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-008 is #8; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Direct typed broker worker bridge and shadow orchestration. Preserve current production behavior unless the scoped acceptance criteria and required gates have been satisfied. Any live trading cutover is outside this packet unless explicitly specified.

## Current evidence and source boundary
Current coupling: RSAssistant sends !rsa via Discord, parses replies and reads per-broker JSON from shared volumes/db. The fork has no confirmed server API; ULT-MA executor assumes one.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These facts are not equivalent. Do not implement on stale assumptions.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: broker response contracts and order-intent states stable; check ULT-MA disabled HTTP assumption and existing local Docker changes. Require read-only shadow before any live dispatch cutover.**

The implementer must mark this packet `In Progress` in `TRACKER.md` and `INDEX.md` **only after** reviewing dependency completion summaries and confirming the named files/symbols on the *then-current* canonical main. If drift changes SQL/IPC/trading semantics, refresh packet and record rationale before execution. No executing `Draft` or `Blocked`.

## Exact target files and symbols
- `rsassistant/services/order_orchestration.py`
- `utils/order_exec.py`
- `rsassistant/services/broker_protocol.py (new)`
- `rsassistant/workers/broker_bridge.py (new)`
- `rsassistant/persistence/orders.py`
- `docker-compose.yml`
- `config/.env.example`
- `unittests/broker_protocol_test.py (new)`

## Required implementation, in order
1. Specify versioned request/response schema for list_accounts, positions, get_order, activities, submit_order, cancel_order and health, each with opaque correlation/idempotency key and typed error class. Unsupported capability explicit.
2. Choose local Unix-domain socket or private authenticated IPC; broker worker never accesses RSAssistant SQLite file directly. Restrict socket and worker session credentials to service user; enforce request size/timeouts and structured result codes.
3. Use write-ahead order intent + atomic dispatch claim. A transport timeout yields 'unknown, needs_reconciliation', not automatic retry. Keep exchange order id distinct from command id and local plan id.
4. Build shadow bridge accepting mock/fixture adapter: run request/response and compare holdings/health without mutating broker positions. Legacy Discord path stays for production with feature flag default off.
5. Remove direct Discord coupling only after Fidelity and additional broker parity packets. Import license headers and dependency constraints when moving broker code.

### Invariants / validation boundaries
- No brokerage command may be presumed filled from Discord send alone; preserve reported status and provenance.
- Do not resurrect auto-buys for old events when replaying stale or missing evidence; preserve the split-event durable claim from TP-20261013-001.
- New state belongs to canonical SQLite; legacy JSON/CSV may be fixtures or transitional input only.
- Tests must use temporary databases and mock broker transport. No live order, no credential dump, no production DB fixtures.
- Preserve original open split watches and all unresolved position/order evidence, including BTOC/KNDI/FRGT/OBAI if still outstanding at execution time.
- Include one reversible data migration strategy when schema changes and a downgrade/rollback note in the completion summary.

## Focused and full validation
- `python -m unittest unittests.broker_protocol_test unittests.order_dispatcher_test`
- `duplicate key, lost ack, crash+restart, invalid protocol, version mismatch, unauthorized socket, oversized payload, mock no-order invariant`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Production acceptance requires an operator-reviewed read-only parity report; record exact timestamps, source versions and unknowns.

## Acceptance criteria
- [ ] Typed IPC can retrieve mock positions and incident status
- [ ] Unknown dispatch cannot issue second broker order
- [ ] No direct database write from worker
- [ ] Production trading remains on old path pending adapter pilot approval
- [ ] No regression to event idempotency, existing broker order queues or account historical data.
- [ ] Completion summary describes coverage, schema/backfill, observed runtime differences and any remaining human review.

## Explicit non-goals
No mass broker port, no live trading canary, no public HTTP API, no new Discord command surface.

## Handoff / completion report
On verified completion move exactly this canonical file from `active/` to `completed/`, update `INDEX.md` and `TRACKER.md` atomically, and write `docs/task-packets/summaries/TP-20261016-008-SUMMARY.md` (Outcome, Validation, Process Feedback, Next Handoff). State next packet TP-20261016-009 and whether a fresh planning review is required; never claim production parity from mocks only.
