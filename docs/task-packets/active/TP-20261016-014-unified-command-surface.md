# TP-20261016-014: Replace scattered commands with one typed operator interface

**Packet ID:** TP-20261016-014  
**Status:** In Progress
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-014-unified-command-surface.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P1  
**Depends on:** TP-20261016-008, -012, -013  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-014 is #14; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Replace scattered commands with one typed operator interface. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Current about 39 prefix commands spread over ten cogs, plus ULT-MA commands and separate !rsa bot. Overlap among watchlists/split monitors, order queue/history, ownership and performance.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: API shape, permissions and reconciliation semantics must be stable; review current main command list incl local splitreview/splitresolve/splitreplace/watcherstatus. Do not remove old aliases until telemetry and compatibility review.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `rsassistant/bot/core.py`
- `rsassistant/bot/cogs/orders.py`
- `rsassistant/bot/cogs/holdings.py`
- `rsassistant/bot/cogs/split_monitor.py`
- `rsassistant/bot/cogs/accounts.py`
- `rsassistant/bot/cogs/watchlist.py`
- `rsassistant/bot/cogs/reporting.py`
- `rsassistant/bot/cogs/performance.py`
- `rsassistant/bot/cogs/admin.py`
- `rsassistant/services/ (query facade)`
- `unittests/command_contract_test.py (new)`

## Required changes / implementation order
1. Create app_commands Discord slash tree: /rs status; /rs splits list/show/review/approve; /rs portfolio accounts/holdings/refresh/history; /rs orders list/show/reconcile/cancel; /rs trade preview/buy/sell; /rs reports pnl/roundups/performance; /rs system health/jobs/config.
2. Commands call typed application services only; no direct SQLite writes, file edits or Discord-to-Discord order messages inside handlers. Application services are UI-agnostic for later local dashboard.
3. Group interactions into paginated embeds with account-safe redaction and evidence links, output statuses UNKNOWN, STALE, PENDING explicitly. Trade actions require permission check, preview+confirmation, amounts and account scope.
4. Preserve old prefix commands as read-only redirects or explicitly mapped compatibility aliases during transition; collect deprecation telemetry and identify commands with live order side effects.
5. Move owner/admin maintenance commands to protected ops layer, remove `..patchautorsa`/runtime Git pull triggers after deployment safety is ready. Keep ULT-MA isolated and disabled by default.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.command_contract_test unittests.discord_permissions_test unittests.command_error_handler_test`
- `permissions operator vs viewer; no live trades on read-only commands; alias equivalence; pagination; stale positions`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] One discoverable /rs command tree covers normal workflows
- [ ] No privileged state change possible through a read-only alias
- [ ] Every displayed order/position has freshness and evidence status
- [ ] Old aliases can be rolled back without losing events
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No UI-controlled implicit autobuys, no arbitrary SQL execution, no public API exposure.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-014-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-015. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Progress log (2026-10-16)
Done (read-only audit, no command changed or removed): `scripts/command_inventory.py` + generated `docs/command-inventory.md` — 40 commands from the cog sources via AST. Authorization audit: every trade/destructive command (`order`, `liquidate`, `remove`, `queue_run`, `restart`, `shutdown`, `patchautorsa`, `clear*`, `split*` mutators, etc.) carries a decorator check (`admin_only` or `has_permissions`); the 15 commands with no decorator are read-only reporting (`aliases, all, brokerlist, brokerwith, grouplist, history, lastorder, orders, ownersummary, performance, queue, splitlist, splitstatus, top, watchlist`). Note `queue` (list) is unchecked while `queue_run` is checked — verify intent.
**Remaining (gated on a stable API + telemetry):** typed operator interface, alias retention, any removal. Status stays In Progress.
