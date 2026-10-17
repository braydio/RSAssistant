# TP-20261016-013: Account-level split credits, cash-in-lieu and sale reconciliation

**Packet ID:** TP-20261016-013  
**Status:** Draft  
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-013-corporate-action-settlement-reconciliation.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-004, -005, -008, -012  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-013 is #13; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Account-level split credits, cash-in-lieu and sale reconciliation. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Legacy ..xsplits caches one-share holdings by broker/ticker and treats 'one share' as a candidate, but may not prove credit origin or account; split_monitor status updates historically deleted overdue watches.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**REFRESH + HUMAN REQUIRED: after broker activity support and policy classifier evidence are landed, confirm available corporate action statements and live split watches. Backfill in read-only dry run first; ensure no open sale is discarded.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `rsassistant/services/alert_processing.py`
- `rsassistant/bot/cogs/split_monitor.py`
- `rsassistant/persistence/reverse_splits.py`
- `rsassistant/persistence/schema.py`
- `utils/split_watch_utils.py`
- `rsassistant/services/corporate_action_reconciliation.py (new)`
- `unittests/corporate_action_reconciliation_test.py (new)`

## Required changes / implementation order
1. Add action_participations(action_id, canonical_account_id, intended_qty, confirmed_pre_qty, expected_post_qty, deadline, state), corporate_action_adjustments(account_id, action_id, credited_qty, cash_in_lieu, broker_activity_id, source, confidence, observed_at), and reconciliation audit history. SQLite migration append-only; preserve v10 intent tables.
2. Calculate expected post-split holdings using exact Decimal quantities and ratio, differentiate ordinary reverse-split conversion from credited extra share; never treat quantity==1 alone as proof of roundup.
3. Reconcile each participating account against broker activities, executions and timed position deltas. Classify pending, whole-share-credited, cash-in-lieu, partial, missing and conflicting with evidence sources. Late settlements reopen review safely.
4. Retain overdue selling-phase watches until all actually bought accounts have verified sale/reconciliation or documented manual disposition. Use event/account ID, never ticker-only as final identity.
5. Generate sell *candidates* with inspected quantities; order execution requires explicit approved policy and broker-capability proof; reconcile confirmed fill before closing.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.corporate_action_reconciliation_test unittests.split_watch_utils_test`
- `decimal rounding, DTC-only round up, settled late, missing account, cancelled buy, partial fill, duplicate activities, crash and rescan idempotency`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] Can evidence each whole-share credit or cash payout at account level
- [ ] No automatic sell on an ordinary pre-existing one-share holding
- [ ] Completed split remains auditable and unknown orders cannot auto-close
- [ ] BTOC/KNDI/FRGT/OBAI state preserved or explicitly reconciled
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No assumptions of guaranteed brokerage rounding, no live sale until order integration is approved.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-013-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-014. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Progress log (2026-10-16)
Not started — gated (REFRESH + HUMAN): requires broker activity/fill evidence (TP-004 table exists, no live source), policy evidence (TP-012 partial) and corporate-action statements from the owner. Four watches (BTOC/KNDI/FRGT/OBAI) remain `buying` and must not be discarded by any backfill.
