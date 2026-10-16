# TP-20261016-007: Secure guided reauthentication and bounded recovery

**Packet ID:** TP-20261016-007  
**Status:** Draft  
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-007-guided-broker-reauth-and-recovery.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P1  
**Depends on:** TP-20261016-006  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-007 is #7; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Secure guided reauthentication and bounded recovery. Preserve current production behavior unless the scoped acceptance criteria and required gates have been satisfied. Any live trading cutover is outside this packet unless explicitly specified.

## Current evidence and source boundary
Wells Fargo requires phone approval on each login, Vanguard SMS code currently via terminal/Discord, Chase stale profile locks, Fidelity verified with saved profile; Fennel 429 is not an authentication error.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These facts are not equivalent. Do not implement on stale assumptions.

## Hard prerequisite / required refresh gate
**REFRESH + HUMAN REQUIRED: confirm per-broker MFA flows and operator-authenticated local UI, credential retention, and sandboxed session tests. Do not expose MFA via public Discord.**

The implementer must mark this packet `In Progress` in `TRACKER.md` and `INDEX.md` **only after** reviewing dependency completion summaries and confirming the named files/symbols on the *then-current* canonical main. If drift changes SQL/IPC/trading semantics, refresh packet and record rationale before execution. No executing `Draft` or `Blocked`.

## Exact target files and symbols
- `rsassistant/services/broker_recovery.py (new)`
- `rsassistant/services/broker_health.py`
- `rsassistant/persistence/broker_incidents.py`
- `scripts/env_gui.py (extract secure UI rather than reuse Codex editor indiscriminately)`
- `rsassistant/bot/cogs/primary_channel_error_watcher.py`
- `config/.env.example`
- `unittests/broker_recovery_test.py (new)`

## Required implementation, in order
1. Add recovery strategies by typed failure: one bounded browser restart, ephemeral lock cleanup ONLY for proven dead local process, configured rate-limit Retry-After, explicit reauth challenge, provider outage cooldown, code regression escalation.
2. Queue single-flight session recovery per login profile; one profile may host many brokerage accounts. Circuit breaker suspends new trade submissions, not read-only incident and reconciliation services.
3. Implement operator-authenticated local-only recovery endpoint with CSRF/session expiration, short-lived single-use challenge handles. Discord only deep-links to local protected UI; never asks for OTP as a public channel message.
4. Record incident/attempt/verification outcome; classify completed authentication separate from positions read and order write capabilities. No automatic trade as a 'connectivity test'.
5. For code-level breakages, capture sanitized reproduction fixture and propose human-reviewed patch with tests; prohibit untrusted Codex stdout/stderr in Discord and autonomous production deploy.

### Invariants / validation boundaries
- No brokerage command may be presumed filled from Discord send alone; preserve reported status and provenance.
- Do not resurrect auto-buys for old events when replaying stale or missing evidence; preserve the split-event durable claim from TP-20261013-001.
- New state belongs to canonical SQLite; legacy JSON/CSV may be fixtures or transitional input only.
- Tests must use temporary databases and mock broker transport. No live order, no credential dump, no production DB fixtures.
- Preserve original open split watches and all unresolved position/order evidence, including BTOC/KNDI/FRGT/OBAI if still outstanding at execution time.
- Include one reversible data migration strategy when schema changes and a downgrade/rollback note in the completion summary.

## Focused and full validation
- `python -m unittest unittests.broker_recovery_test`
- `challenge expires/reused token rejected, lock cleanup refuses active PIDs, retry budget honored, shared incident coalescence, circuit breaker blocks order submission`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Production acceptance requires an operator-reviewed read-only parity report; record exact timestamps, source versions and unknowns.

## Acceptance criteria
- [ ] Operator reaches correct failing profile from one alert
- [ ] MFA never posted/stored in Discord or logs
- [ ] Idempotent recover/retest with no orders submitted
- [ ] Transient failures self-heal and provider outages back off
- [ ] No regression to event idempotency, existing broker order queues or account historical data.
- [ ] Completion summary describes coverage, schema/backfill, observed runtime differences and any remaining human review.

## Explicit non-goals
No bypass of brokerage MFA, no scraping stored OTPs or account passwords, no automatic commit/deploy.

## Handoff / completion report
On verified completion move exactly this canonical file from `active/` to `completed/`, update `INDEX.md` and `TRACKER.md` atomically, and write `docs/task-packets/summaries/TP-20261016-007-SUMMARY.md` (Outcome, Validation, Process Feedback, Next Handoff). State next packet TP-20261016-008 and whether a fresh planning review is required; never claim production parity from mocks only.
