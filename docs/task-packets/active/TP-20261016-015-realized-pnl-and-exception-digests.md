# TP-20261016-015: Evidence-grade performance reporting and exception monitoring

**Packet ID:** TP-20261016-015  
**Status:** In Progress
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-015-realized-pnl-and-exception-digests.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P2  
**Depends on:** TP-20261016-004, -005, -013, -014  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-015 is #15; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Evidence-grade performance reporting and exception monitoring. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Existing performance views are account-value snapshots; send logs don't establish execution. Need outcome-aware by-action profitability, missed earnings/cash payments, broker reliability, recovered positions and failure trends.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: compare available broker fills/fees/activities and account cash flow histories after 013; no estimate may be presented as realized profit.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `rsassistant/services/performance.py`
- `rsassistant/persistence/performance.py`
- `rsassistant/bot/cogs/performance.py`
- `rsassistant/services/alert_processing.py`
- `rsassistant/bot/tasks.py`
- `rsassistant/services/roundup_reporting.py (new)`
- `unittests/roundup_reporting_test.py (new)`

## Required changes / implementation order
1. Define net realized per action/account as verified sale proceeds plus verified corporate-action cash less acquisition cost and known execution/other fees; use Decimal and nullable unknown components.
2. Keep cash flow and mark-to-market performance separate from realized round-up P&L. Exclude invented fills, quote fallback prices and unmatched legacy sends; group those under unverified.
3. Build historical backfill in dry-run mode from SEC/discovery evidence, broker order/position/activity snapshots with reconciliation report and review queue, no historical autobuy.
4. Scheduled daily exception digest emits changed items only: pending broker MFA, rate limits, missing credit, stale positions, ambiguous order, late settlement; periodic weekly broker yield/MTTR effectiveness.
5. Expose /rs reports roundups/pnl/brokers with date and broker filters and data completeness badge. Preserve explicit unknown vs zero.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.roundup_reporting_test unittests.performance_service_test`
- `fees, partial fills, missing costs, cash-in-lieu, splits before/after sale, replayed statements, currency/Decimal consistency`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] Realized figures trace to broker evidence, not Discord guesses
- [ ] Incomplete data reported separately and transparently
- [ ] Daily digests do not spam repeated unchanged incidents
- [ ] Backfill performs zero order submissions
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No speculative P&L forecasts described as realized, no live trades, no bulk brokerage scraping.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-015-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-016. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Progress log (2026-10-16)
Done (exception-monitoring half only): `scripts/operator_status.py` — read-only one-screen status (schema version, per-broker holdings freshness, recent snapshot imports, open incidents, order intents lacking broker evidence, open split watches, newest OrderHistory row). Run against production (schema still v10 until redeploy): holdings fresh 2026-10-16 04:18 for all six live brokers; OrderHistory newest 2026-07-30; 4 split watches in `buying`.
**Blocked / not started:** evidence-grade realized P&L — needs broker fills/fees/cash-flow (TP-004's `execution_fills` is intentionally empty until broker activity exists, TP-008–010 live adapters). No estimate may be presented as realized profit. Status stays In Progress.
