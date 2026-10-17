# TP-20261016-011: Preserve and selectively migrate remaining broker connections

**Packet ID:** TP-20261016-011  
**Status:** Draft  
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-011-secondary-broker-adapters.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P1  
**Depends on:** TP-20261016-010, TP-20261016-017  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 18 canonical packets; IDs 017/018 inserted at dependency gates into the original train, TP-20261016-011 is #11; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Preserve and selectively migrate remaining broker connections. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Wells Fargo device approval + Selenium, Chase network timeout after browser repairs/0 accounts, Schwab timeout, Vanguard SMS prompt; SoFi/Webull stale. Modern fork exposes 16 brokers but no recent evidence of use for several.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**HUMAN + REFRESH REQUIRED: owner confirms active broker priority and which adapters to retain; preserve uncommitted AutoRSA-GUI.local Chase/Fennel/WF changes; inspect licensing and API/driver viability before coding. Unsupported adapters remain disabled, not silently deleted.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `auto-rsa/src/brokerages/wellsfargo_api.py`
- `auto-rsa/src/brokerages/chase_api.py`
- `auto-rsa/src/brokerages/schwab_api.py`
- `auto-rsa/src/brokerages/sofi_api.py`
- `auto-rsa/src/brokerages/webull_api.py`
- `auto-rsa/src/brokerages/vanguard_api.py`
- `auto-rsa/src/brokers.py`
- `src/rsassistant/integrations/brokers/ (adapter registry)`
- `unittests/secondary_broker_adapters_test.py (new)`

## Required changes / implementation order
1. Diff modern fork against dirty AutoRSA-GUI.local broker implementations; preserve each unique fix as reviewed patch/commit before cleanup; do not assume newest directory is authoritative for every broker.
2. Build per-broker capability matrix (auth type, read holdings, orders, activities, user presence, day-1/settlement behavior, confidence) with evidence and known failure mode.
3. Port Wells Fargo first with phone approval through secure recovery UI; then Schwab, Chase, SoFi, Webull by owner's priority. Vanguard stays interactive until secure SMS challenge integration. Remaining listed brokers become supported/disabled explicitly.
4. Group browser-system incidents (Xvfb, webdriver, profile lock, sandbox) before broker-specific repair. Preserve last-known data and mark stale on failed reads; avoid full-login health loops.
5. Run smoke and shadow tests for each supported adapter, preserve licensing and source provenance; generate acceptance matrix and release only per broker after read-only and operator-approved trade parity.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.secondary_broker_adapters_test unittests.broker_recovery_test`
- `mock driver missing, stale locks, device approval, no accounts, timeout, crash recovery; broker-specific fixtures`
- `per-broker readonly shadow report + isolated smoke tests`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] Each installed adapter has a capability/status entry and recovery path
- [ ] Dirty local broker fixes preserved in Git before deleting GUI copies
- [ ] No unsupported broker attempts produce false successful fills
- [ ] No broker-specific failure disables unrelated adapters
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No requirement to make all 16 brokers functional; no automatic MFA bypass or credential export.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-011-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-012. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Architecture decision amendment (2026-10-16): prioritize native broker support, not all-16 port

- **New dependency:** TP-017's owned SDK and TP-009/010 acceptance evidence. Implement `rsassistant/integrations/brokers/{wellsfargo,schwab,chase,sofi,webull,vanguard}/` selectively in the existing package (not speculative `src/rsassistant/...`).
- Preserve and review the locally modified `AutoRSA-GUI.local` Chase/Fennel/Wells Fargo files before deleting copies. Their functionality may inform independent requirements and tests; **do not copy GPL implementation** without legal/licensing review.
- Prefer documented official broker API/access or reviewed maintained SDK, then independently developed browser client where needed. Do not claim undocumented endpoints are stable or bypass MFA.
- Prioritize Wells Fargo with guided device approval, then Schwab/Chase/SoFi/Webull according to confirmed active usage; Vanguard stays interactive. Keep unsupported low-usage legacy broker behind a pinned separately isolated worker or explicitly disable it, do not spend effort recreating all 16.
- Create a per-broker capability/maintenance matrix: read accounts/positions/orders/activities, order submission only if authorized, auth/recovery method, last successful independent broker session, source/SDK version/license, current operational value, fallback choice. Deliver matrix to TP-018.
- Read-only shadow parity and profile hold must be proven before changing actual routing for any one broker.

