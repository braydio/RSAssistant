# TP-20261016-006: Broker connection health contract and incident registry

**Packet ID:** TP-20261016-006  
**Status:** Complete
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261016-006-broker-connection-health-incidents.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P1  
**Depends on:** TP-20261016-005  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-006 is #6; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Broker connection health contract and incident registry. Preserve current production behavior unless the scoped acceptance criteria and required gates have been satisfied. Any live trading cutover is outside this packet unless explicitly specified.

## Current evidence and source boundary
Fidelity CLI sandbox flag generated a false alert; real live Fidelity verified. Chase network timeout/0 accounts, Fennel HTTP 429, Wells Fargo device challenge, Schwab timeout, Public empty positions.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These facts are not equivalent. Do not implement on stale assumptions.

## Hard prerequisite / required refresh gate
**Dependency check: canonical login/account scope stable; refresh broker adapter capability inventory after 005. Do not implement generic browser login pings.**

The implementer must mark this packet `In Progress` in `TRACKER.md` and `INDEX.md` **only after** reviewing dependency completion summaries and confirming the named files/symbols on the *then-current* canonical main. If drift changes SQL/IPC/trading semantics, refresh packet and record rationale before execution. No executing `Draft` or `Blocked`.

## Exact target files and symbols
- `rsassistant/services/broker_health.py (new)`
- `rsassistant/persistence/broker_incidents.py (new)`
- `rsassistant/persistence/schema.py`
- `rsassistant/bot/tasks.py`
- `rsassistant/bot/cogs/reporting.py`
- `utils/logging_setup.py`
- `unittests/broker_health_test.py (new)`

## Required implementation, in order
1. Define typed LoginProfileHealth(account_scope, status, capabilities, checked_at, last_success, source_commit, error_code); statuses healthy/degraded/reauth_required/challenge_pending/provider_unavailable/adapter_broken/unknown/disabled.
2. Append migration with broker_incidents and broker_incident_events, unique open incident per normalized (profile,error_class,root_cause). Parent infra incidents deduplicate shared Xvfb/Chromium failures.
3. Capture structured exceptions before Discord output; scrub tokens, OTP, cookies, URLs with state, full account numbers, and HTML. Severity and action hints are pure functions.
4. Run low-cost read-only health validation using already authenticated sessions; adaptive cadence keyed to upcoming approved orders. Freshness and capability failures don't automatically mean login failure.
5. Produce operator-only connection status and change-only alerts. Disable new operations per affected profile on ambiguous execution, preserve monitoring.

### Invariants / validation boundaries
- No brokerage command may be presumed filled from Discord send alone; preserve reported status and provenance.
- Do not resurrect auto-buys for old events when replaying stale or missing evidence; preserve the split-event durable claim from TP-20261013-001.
- New state belongs to canonical SQLite; legacy JSON/CSV may be fixtures or transitional input only.
- Tests must use temporary databases and mock broker transport. No live order, no credential dump, no production DB fixtures.
- Preserve original open split watches and all unresolved position/order evidence, including BTOC/KNDI/FRGT/OBAI if still outstanding at execution time.
- Include one reversible data migration strategy when schema changes and a downgrade/rollback note in the completion summary.

## Focused and full validation
- `python -m unittest unittests.broker_health_test`
- `simulate wrong Docker mode vs true broken browser, MFA needed, 429, shared driver problem, duplicate incidents, permission boundary`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Production acceptance requires an operator-reviewed read-only parity report; record exact timestamps, source versions and unknowns.

## Acceptance criteria
- [ ] Per-login status is typed and reproducible
- [ ] One infra incident instead of duplicated brokerage incidents
- [ ] No secrets emitted to Discord or normal app logs
- [ ] Transient recovery closes incident without trade side effects
- [ ] No regression to event idempotency, existing broker order queues or account historical data.
- [ ] Completion summary describes coverage, schema/backfill, observed runtime differences and any remaining human review.

## Explicit non-goals
No actual broker repair, no MFA code capture, no auto-code-deployment.

## Handoff / completion report
On verified completion move exactly this canonical file from `active/` to `completed/`, update `INDEX.md` and `TRACKER.md` atomically, and write `docs/task-packets/summaries/TP-20261016-006-SUMMARY.md` (Outcome, Validation, Process Feedback, Next Handoff). State next packet TP-20261016-007 and whether a fresh planning review is required; never claim production parity from mocks only.
