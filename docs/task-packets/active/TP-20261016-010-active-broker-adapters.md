# TP-20261016-010: Migrate Fennel, Public and Robinhood through the typed worker

**Packet ID:** TP-20261016-010  
**Status:** In Progress
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-010-active-broker-adapters.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P1  
**Depends on:** TP-20261016-009, TP-20261016-017  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 18 canonical packets; IDs 017/018 inserted at dependency gates into the original train, TP-20261016-010 is #10; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Migrate Fennel, Public and Robinhood through the typed worker. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Operator active snapshot shows Fennel, Public, Robinhood fresh; Fennel rate limiting affects orders; Public pull sometimes returns empty holdings while older history shows activity; Robinhood quote API returns 400 for certain tickers.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: freeze adapter interface from Fidelity pilot; verify Fennel 429/Retry-After, Public empty-vs-held contradiction, Robinhood 400 quote failures. Obtain fresh per-broker parity fixtures, then allow controlled cutover per broker.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `auto-rsa/src/brokerages/fennel_api.py`
- `auto-rsa/src/brokerages/public_api.py`
- `auto-rsa/src/brokerages/robinhood_api.py`
- `src/rsassistant/integrations/brokers/fennel/adapter.py (new)`
- `src/rsassistant/integrations/brokers/public/adapter.py (new)`
- `src/rsassistant/integrations/brokers/robinhood/adapter.py (new)`
- `rsassistant/services/broker_health.py`
- `unittests/active_broker_adapters_test.py (new)`

## Required changes / implementation order
1. Adapt one broker at a time using pinned fork/version and vendor license inventory. Model login profiles and named subaccounts separately; normalized response includes snapshot timestamp, complete/partial flag.
2. For Fennel implement shared per-profile token bucket/backoff with Retry-After and single-flight auth; rate limits must never spawn duplicate orders.
3. For Public distinguish a valid zero-position account from an unparseable/partial positions response; don't replace the entire canonical snapshot with empty holdings if the fetch was incomplete.
4. For Robinhood quote HTTP 400 means pricing unavailable for that ticker; do not block holdings/fills or synthesize $0 execution price.
5. Shadow compare each broker's position/activity events and 1:1 order status. Perform canary and rollback separately per broker with human authorization. Preserve existing pending orders during any switch.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.active_broker_adapters_test unittests.broker_protocol_test`
- `simulate 429 with Retry-After; Public zero positions vs parser failure; Robinhood quote 400; partial broker-wide scan; replayed order`
- `read-only operator parity report by broker/account`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] All three active adapters provide typed holdings and classified failures
- [ ] No stale/null positions overwrite known-good snapshot
- [ ] 429 backoff reduces retry churn without increasing trade frequency
- [ ] Broker-specific rollback and provenance complete
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No mass cutover, no broker order frequency change, no assumptions about quote availability.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-010-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-011. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Progress log (2026-10-16)
Done (read-only): generic `SnapshotBrokerAdapter` (`rsassistant/integrations/brokers/snapshot.py`; Fidelity adapter now a thin subclass) and `scripts/broker_shadow_parity.py --broker X`. Live parity vs `holdings_current` at 2026-10-16: fidelity 114/114, fennel 110/110, public 114/114, robinhood 185/185, vanguard 5/5, wellsfargo 17/17 positions — zero only-in-either, zero quantity mismatches.
Findings that refresh this packet: (1) **Public "empty holdings" contradiction resolved** — earlier "empty" came from CLI (non-docker) runs; live data has 2 Public accounts / 114 positions. (2) **Fennel 429** is a broker rejection arriving as chat text (`Fennel 1 Account N: Error placing order: ... status code 429`) that matched no order pattern and was only logged as "No match found"; `fennel_api.py` has no rate-limit/Retry-After handling at all. Now parsed into a `rejected` receipt + `rate_limited` incident (`parsing_utils._record_unmatched_failure`). (3) Robinhood HTTP 400 quote failures: not reproducible from current logs (container logs were reset on rebuild); needs a fresh capture.
**Remaining:** real adapters for Fennel/Public/Robinhood through the worker, Retry-After honouring in the Fennel path, per-broker cutover — all need live sessions and owner approval. Status stays In Progress.

## Architecture decision amendment (2026-10-16): native clients, not import-based wrappers

**The implementation target is native RSAssistant adapters** in `rsassistant/integrations/brokers/{fennel,public,robinhood}/`, using TP-017's API and capability registry. The existing `SnapshotBrokerAdapter` remains a regression reference, not native brokerage capability.

- **New dependency:** TP-017 must be complete; Fidelity TP-009 establishes the SDK's first broker-facing validation and canary conditions. Retain packet's In Progress status and existing factual progress.
- Fennel: choose suitable official or reviewed third-party SDK if supported; otherwise write an independently maintained HTTP client within provider terms. Reuse typed broker `RateLimited(retry_after)` recovery; test 429 before submit and rejection vs unknown. Cooldown must prohibit *actual broker request* and never create a duplicate order.
- Public: native adapter must differentiate a verified empty account from a failed or partial response, including source timestamp; compare broker order activity for the 94 September 29 sell commands. Do not treat 21 remaining positions as evidence the others filled.
- Robinhood: evaluate maintained SDK/library license and actual supported capabilities. Quote HTTP 400 cannot suppress holdings, account, or verified order activity; never impute execution price from quote. Preserve correct broker order IDs.
- Use `rsassistant/integrations/brokers/` (existing package) rather than speculative `src/rsassistant/` paths. For each broker create only the capabilities genuinely supported; `UNSUPPORTED` is a valid outcome.
- Mutating `submit_order` is off until independently sourced accounts/positions/activities match in read-only shadow mode, safe-liquidate semantics and per-profile execution hold are tested, and owner authorizes a canary separately.
- Add fixtures for 429/Retry-After (not retry unknown), partial account enumeration, source freshness, native-to-legacy comparison, provider drift and legacy fallback without re-execution.

