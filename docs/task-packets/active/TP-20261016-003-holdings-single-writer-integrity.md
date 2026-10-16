# TP-20261016-003: Verify and restore canonical holdings ingestion

**Packet ID:** TP-20261016-003  
**Status:** Draft  
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-003-holdings-single-writer-integrity.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-002  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-003 is #3; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Verify and restore canonical holdings ingestion. Preserve current production behavior unless the scoped acceptance criteria and required gates have been satisfied. Any live trading cutover is outside this packet unless explicitly specified.

## Current evidence and source boundary
Reported production holdings_current = one pytest fixture row, JSON snapshot ~545 positions and Fidelity last ingested 2026-08-28. Local fix for Timestamp normalization, nested write deadlock and import false success was deployed but not yet validated end to end.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These facts are not equivalent. Do not implement on stale assumptions.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED after 002: compare 83a6b00 importer/csv_utils fixes and live holdings_current/snapshot timestamps with resulting main. Require a new read-only Fidelity snapshot; never trust previously marked-imported mtime.**

The implementer must mark this packet `In Progress` in `TRACKER.md` and `INDEX.md` **only after** reviewing dependency completion summaries and confirming the named files/symbols on the *then-current* canonical main. If drift changes SQL/IPC/trading semantics, refresh packet and record rationale before execution. No executing `Draft` or `Blocked`.

## Exact target files and symbols
- `utils/holdings_importer.py`
- `utils/csv_utils.py`
- `rsassistant/persistence/holdings.py`
- `rsassistant/persistence/accounts.py`
- `rsassistant/persistence/performance.py`
- `rsassistant/bot/cogs/holdings.py`
- `unittests/holdings_importer_test.py`
- `unittests/csv_utils_test.py`

## Required implementation, in order
1. Define one committed snapshot identity (source path/hash, observed_at, broker/login scope, record count) in holdings_refreshes. If current schema lacks required fields, append non-destructive migration; don't make JSON operational authority.
2. Ensure normalization retains every Timestamp/observed_at and negative/empty positions don't masquerade as missing accounts; rejects missing source timestamp with explicit code. All inserts/aliases/nickname lookups sharing a transaction use one SQLite connection; no nested writer.
3. Write stage+validate+atomic activate (readers see old complete snapshot or new complete snapshot), durable import status and error. Mark source hash successful ONLY after activation; failure is retryable and never announced as imported.
4. Preserve clean historical account value snapshots and inspect test-generated BrokerA/B rows separately. Do not clear holdings_current or discard real records before account identity migration.
5. Add read-only reconciliation report: counts and freshness per broker vs JSON and SQL plus deterministic reprocessing for a previously failed source hash.

### Invariants / validation boundaries
- No brokerage command may be presumed filled from Discord send alone; preserve reported status and provenance.
- Do not resurrect auto-buys for old events when replaying stale or missing evidence; preserve the split-event durable claim from TP-20261013-001.
- New state belongs to canonical SQLite; legacy JSON/CSV may be fixtures or transitional input only.
- Tests must use temporary databases and mock broker transport. No live order, no credential dump, no production DB fixtures.
- Preserve original open split watches and all unresolved position/order evidence, including BTOC/KNDI/FRGT/OBAI if still outstanding at execution time.
- Include one reversible data migration strategy when schema changes and a downgrade/rollback note in the completion summary.

## Focused and full validation
- `python -m unittest unittests.holdings_importer_test unittests.csv_utils_test unittests.holdings_repository_test`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `synthetic two-writer SQLite rollback/lock test, same-content idempotency, partial broker failure, missing Timestamp, stateful staging regression`
- `python -m compileall -q rsassistant utils unittests scripts`
- Production acceptance requires an operator-reviewed read-only parity report; record exact timestamps, source versions and unknowns.

## Acceptance criteria
- [ ] Fresh Fidelity-only holdings appear in authoritative SQL with expected account/position counts
- [ ] Error returns failure and does not advance imported marker
- [ ] Retry succeeds once without duplicate historical records
- [ ] No production fixtures created by tests
- [ ] No regression to event idempotency, existing broker order queues or account historical data.
- [ ] Completion summary describes coverage, schema/backfill, observed runtime differences and any remaining human review.

## Explicit non-goals
No automated trades, no historic account deletion, no auto-rsa rewrite, no new dashboards.

## Handoff / completion report
On verified completion move exactly this canonical file from `active/` to `completed/`, update `INDEX.md` and `TRACKER.md` atomically, and write `docs/task-packets/summaries/TP-20261016-003-SUMMARY.md` (Outcome, Validation, Process Feedback, Next Handoff). State next packet TP-20261016-004 and whether a fresh planning review is required; never claim production parity from mocks only.
