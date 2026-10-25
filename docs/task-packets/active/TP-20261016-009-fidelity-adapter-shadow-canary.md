# TP-20261016-009: Extract and shadow-validate the Fidelity broker adapter

**Packet ID:** TP-20261016-009  
**Status:** In Progress
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-009-fidelity-adapter-shadow-canary.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-008, TP-20261016-017 (remaining live native work)  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 18 canonical packets; IDs 017/018 inserted at dependency gates into the original train, TP-20261016-009 is #9; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Extract and shadow-validate the Fidelity broker adapter. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Fork src/brokerages/fidelity_api.py ~1,708 lines uses Zendriver; observed successful docker-mode login/25 accounts; false CLI `No usable sandbox` errors when docker_mode=False. Roughly 1,100 'confirmation not detected' traces leave some trades ambiguous. Uncommitted GUI fork code may contain unrelated older fixes.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**HUMAN + REFRESH REQUIRED: owner supplies reviewed Fidelity source, protected activity/order-history observations, and approves any eventual live canary. First run read-only against the actual Docker execution mode (sandbox flags must match).**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `auto-rsa/src/brokerages/fidelity_api.py (nested fork, pin before copy)`
- `src/rsassistant/integrations/brokers/fidelity/adapter.py (new)`
- `rsassistant/workers/broker_bridge.py`
- `rsassistant/services/broker_health.py`
- `rsassistant/persistence/orders.py`
- `unittests/fidelity_adapter_test.py (new)`
- `docker-compose.yml`

## Required changes / implementation order
1. Record pinned git SHA and license provenance of Fidelity source and its webdriver dependencies; snapshot known broker profile behavior. Do not copy creds or cookies into committed test fixtures.
2. Extract operations into the agreed BrokerAdapter: list_accounts, get_positions, get_order_status where possible, account activities if possible, submit_order. If no supported order confirmation API exists, mark unavailable explicitly; never invent success from 'button clicked'.
3. Preserve Zendriver Docker flags and dedicated browser profile paths, add typed BrowserLaunchError/AuthRequired/SessionExpired/SelectorChanged/UnknownOrderOutcome. One login session can enumerate many account IDs.
4. Run read-only Fidelity-only shadows side by side with legacy JSON output, compare full account identity, ticker, quantity, timestamp; keep discrepancy report restricted (account IDs redacted).
5. Gate any trade canary behind explicit human approval, account-specific exposure limit and dry/paper validation. Unknown legacy Fidelity trades must be reconciled from brokerage records before resubmission. Rollback to existing executor without duplicating the order.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.fidelity_adapter_test unittests.broker_protocol_test`
- `offline Zendriver mocks: wrong docker flag, MFA, 25-account pagination, no holdings, retry timeout, ambiguous order, resumed session`
- `read-only live shadow count/positions diff against same-timestamp legacy snapshot`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] Fidelity read-only adapter parity across all permitted login profiles
- [ ] No order marked filled without authoritative evidence
- [ ] One broker failure cannot stop healthy worker/Discord
- [ ] Rollback documented and dry-run tested
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No recreation of lost live fills by guessing; no mass broker migration; no storing credentials in repository.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-009-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-010. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Progress log (2026-10-16)
Done (read-only, no live broker contact): typed errors (`integrations/brokers/fidelity/errors.py`, aligned with `broker_health` classes); `FidelitySnapshotAdapter` (capabilities list_accounts/positions/health; submit/get_order/activities explicitly unsupported — no success is ever inferred from a click); `compare_positions` with account redaction; `scripts/broker_shadow_parity.py`; `PROVENANCE.md` (fork pinned at `110439c`, **GPL-3.0** — no code copied, extraction is an owner licensing decision). Live shadow result: adapter vs `holdings_current` for Fidelity, 114/114 positions, 0 only-in-either, 0 quantity mismatches (21 accounts), 2026-10-16.
**Remaining, HUMAN-gated:** live Zendriver-backed adapter extraction (licensing + reviewed source), protected order-history/activity observations for reconciling ambiguous trades, any trade canary (explicit approval, exposure limit, paper validation). Status stays In Progress.

## Architecture decision amendment (2026-10-16): native Fidelity implementation

**This section supersedes “extract auto-rsa Fidelity module” as the implementation goal.** The goal is an independently maintained **native RSAssistant Fidelity adapter**, not a direct import or copy of `auto-rsa/src/brokerages/fidelity_api.py` into the MIT tree.

- **New dependency:** TP-017 (native SDK, routing registry, provenance), executed before the remaining live work in this packet. TP-008 typed IPC and the snapshot adapter remain valid and completed; do not reopen them.
- Existing `rsassistant/integrations/brokers/fidelity/adapter.py::FidelitySnapshotAdapter`, `rsassistant/integrations/brokers/snapshot.py`, `scripts/broker_shadow_parity.py`, and `rsassistant/integrations/brokers/fidelity/PROVENANCE.md` are **read-only baseline tools**, not live brokerage client implementations. Reported 114/114 position parity is JSON-to-SQL parity only.
- First examine the availability/scope/terms of an official Fidelity brokerage API or permitted SDK. If required capabilities are unavailable, design original native browser integration with typed failure stages and adequate ongoing regression fixtures. Prefer using authorized access and independently authored code; do not copy NelsonDane source (or private session material) without documented license review.
- Work in canonical package paths `rsassistant/integrations/brokers/fidelity/`, NOT the speculative `src/rsassistant/...` location in the original brief. Keep the original pinned GPL worker as a fallback behind IPC until live adapter parity is proven.
- Required native capabilities: account discovery, read-only complete positions, protected session health/recovery, order status, brokerage activity / fills. If order history is not technically available, report `unsupported` and keep **submissions disabled**.
- Verify Docker mode/Xvfb/sandbox behavior with actual deployment flags; compare native broker-fetched data, not the same legacy JSON copied twice. Hold `fidelity:1` and any other profile with ambiguous executions at *actual* dispatcher/worker boundaries.
- **Human refresh gate:** Resolve or explicitly quarantine historical Fidelity ambiguous trades via broker-originated records and obtain owner approval for each live authentication session. No order canary or autotrade authorized.
- Extend tests for real adapter vs snapshot, auth-required, driver/no-sandbox, inaccessible history, profile hold, source/provenance and rollback.

