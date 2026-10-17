# TP-20261016-016: Retire redundant bots and dead code after verified migration

**Packet ID:** TP-20261016-016  
**Status:** Draft  
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-016-legacy-retirement-and-cutover.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-002 through -015 all completed with validated summaries  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-016 is #16; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Retire redundant bots and dead code after verified migration. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Three isolated modules have zero callers in reported static analysis; sql_utils test-only facade; separate auto-rsa Discord process owns legacy credential/session flows; multiple stale GUI clones; ULT-MA assumes missing HTTP endpoint.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**HUMAN CUTOVER REFRESH REQUIRED: verify no open unknown executions or unmatched positions, license review, deployed image pins, DB restore drill and broker-by-broker parity. Requires explicit operator approval for trading dispatch switch.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `utils/reverse_split_parser.py`
- `utils/autobuy_utils.py`
- `utils/audit_watchlist_utils.py`
- `utils/helper_api.py`
- `utils/sql_utils.py`
- `utils/csv_utils.py`
- `utils/parsing_utils.py`
- `utils/update_utils.py`
- `scripts/apply-auto-rsa-patch.sh`
- `patches/auto-rsa-holdings.patch`
- `rsassistant/bot/handlers/on_message.py`
- `rsassistant/bot/core.py`
- `docker-compose.yml`
- `README.md`
- `AGENTS.md`
- `docs/architecture.md`

## Required changes / implementation order
1. Run static import graph (including dynamic cogs/plugins), runtime command registration census and coverage; delete only modules with a proved replacement + no dynamic caller. Move old command names through deprecation aliases with observed usage.
2. Remove auto-rsa Discord bot and text/JSON order/holdings bridge only after each required account has typed adapter parity; preserve original source attribution/license and archived fixtures.
3. Move runtime git update/revert/patch commands out of bot, install pinned immutable images and worker-only auth profile volumes. Run one writer for SQLite; no shared world-writable volume.
4. Write migration guide and rollback: DB online checkpoint, credential backup, v10+ migrations, pinned adapter SHAs, feature flag to restore legacy execution (without automatically replaying unknown intents). Rehearse blue/green on restored clone.
5. Verify outstanding split watches and all historical OrderHistory/sends/account aliases survive. Run staged no-order smoke, then user-approved canary and reconcile, then retire old containers/GUI forks after archiving unique edits.
6. Close modernization umbrella TP-20261003-001 and reassess old Draft TP-20261003-012 for supersession only if all its requirements are met; never silently mark complete.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils scripts unittests`
- `dependency graph/coverage, docker compose config, offline rollback drill, real restored-DB parity report`
- `read-only broker smoke + separately approved canary`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] One authoritative command API, one brokerage worker and one SQLite domain writer
- [ ] All historical orders and split state preserved
- [ ] No unverified order repeated during switch/rollback
- [ ] Every removed module has zero verified callers and replacement tests
- [ ] Rollback proved on cloned environment before production cutover
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No forced consolidation before evidence/canary, no blanket deletion of GUI fork improvements, no unilateral live trading switch.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-016-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: none. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Progress log (2026-10-16)
Not started — HUMAN CUTOVER gate. Nothing may be retired while unknown executions exist (209 sends are `unknown`/`discord_send_only` after backfill, Fidelity "confirmation not detected" orders unreconciled), no live typed-broker adapter exists, and `auto-rsa` (GPL-3.0) is still bind-mounted from an untracked nested clone.
