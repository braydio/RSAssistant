# TP-20261016-012: Unify split discovery and fractional-share evidence

**Packet ID:** TP-20261016-012  
**Status:** In Progress
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-012-split-discovery-policy-provenance.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P1  
**Depends on:** TP-20261016-005, -008, -010  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-012 is #12; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Unify split discovery and fractional-share evidence. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Existing utils/policy_resolver.py + helper_api/reverse_split_parser have overlapping classifiers. Existing alert_processing.resolve_round_up_confirmation treats rounded_to_nearest_whole as confirmed positive; beneficial-owner treatment may differ from DTC-level policy.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: confirm split-event v10 migration and claim logic on merged canonical main, review latest policy resolver changes and broker eligibility. No new autobuys in this packet.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `utils/policy_resolver.py`
- `utils/sec_policy_fetcher.py`
- `utils/openai_utils.py`
- `rsassistant/services/alert_processing.py`
- `rsassistant/services/policy_orchestration.py`
- `rsassistant/bot/handlers/on_message.py`
- `rsassistant/persistence/reverse_splits.py`
- `rsassistant/persistence/schema.py`
- `unittests/policy_resolver_test.py`

## Required changes / implementation order
1. Implement one evidence-based classifier: ROUND_UP_UNCONDITIONAL, ROUND_TO_NEAREST, CASH_IN_LIEU, AGGREGATED_PARTICIPANT, ROUND_DOWN, CONFLICT, UNKNOWN. Do not promote nearest-whole or LLM inference to unconditional round-up.
2. Store SEC accession/release URLs, source fingerprints, extracted exact clause and scope (registered holder/DTC participant/beneficial owner); retain contrary evidence and parser version. Never auto-execute with missing effective date.
3. Deduplicate multi-feed candidates by issuer, corporate action identity, ratio, effective date; preserve historical ticker changes and repeated distinct events on same ticker.
4. Use NASDAQ/issuer/SEC scheduled discovery plus current Discord feed as independent source, with rate-limited fetching, retry/backoff, and audit. LLM resolves/labels evidence for review, never overrides explicit contradictory SEC clause.
5. Expose qualified candidates and confidence with reasons for rejection, but leave autobuy scheduling disabled until reviewed trading policy and account eligibility are proven.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.policy_resolver_test unittests.on_message_roundup_flow_test`
- `fixtures: nearest whole != round up, cash-in-lieu, no fraction, DTC aggregation, conflicting filings, unknown date, source duplicate, changed ticker`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] Every candidate has linked evidence and unambiguous classification
- [ ] No nearest-whole candidate automatically qualifies
- [ ] Repeated Discord/SEC announcements do not create duplicate buy intents
- [ ] Disputed broker scope routes to manual review
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No automatic trade strategy expansion or live orders, no fabricated issuer disclosures.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-012-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-013. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Progress log (2026-10-16)
Done (not wired into autobuy; "no new autobuys" respected): schema **v15** `split_policy_evidence` (keyed `(ticker, split_date)`, source type/URL/fingerprint, exact clause, holder scope, parser version; unique per source+label; rollback = drop table, `user_version=14`); pure `rsassistant/services/split_policy_classifier.py` (`Policy` ROUND_UP_UNCONDITIONAL / ROUND_TO_NEAREST / CASH_IN_LIEU / AGGREGATED_PARTICIPANT / ROUND_DOWN / CONFLICT / UNKNOWN; LLM/feed evidence advisory only and never overrides a contrary primary clause; auto-executable requires primary evidence + effective date; cross-feed dedupe key = issuer+ratio+effective date); `persistence/split_policy_evidence.py`; 8 tests.
**Decision needed from owner (important):** the live `alert_processing.resolve_round_up_confirmation` returns True for `rounded_to_nearest_whole`, which is what currently authorises autobuy. Under nearest-whole a 1-share holder in a 1-for-10 reverse split receives 0 shares (0.1 rounds down), so that treatment can lose the position. The new classifier treats nearest-whole as NOT unconditional. I did not change the live function because it changes trading behaviour; switching autobuy to `classify(...).auto_executable` is a one-line policy change once approved.
**Remaining:** scheduled NASDAQ/SEC discovery with backoff, multi-feed dedupe wiring, candidate/rejection-reason exposure. Status stays In Progress.
