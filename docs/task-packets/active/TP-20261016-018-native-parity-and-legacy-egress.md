# TP-20261016-018: Native brokerage parity, dispatch cutover and upstream retirement gate

**Packet ID:** TP-20261016-018
**Status:** Draft
**Created:** 2026-10-16
**Last updated:** 2026-10-16
**Repository:** braydio/RSAssistant
**Target branch:** main, after local branch reconciliation
**Canonical path:** `docs/task-packets/active/TP-20261016-018-native-parity-and-legacy-egress.md`
**Workstream size:** Bounded per-broker cutover and rollback workstream
**Priority:** P0
**Depends on:** TP-20261016-002, -004, -005, -007, -008, -009, -010, -011, -017; for a specific broker, all relevant adapter + recovery gates must be satisfied
**Execution order:** AFTER adapter train TP-011 / BEFORE final TP-016; no automatic swap to live trading
**Authoring chat:** not-recorded

## Objective

Prove native read, activity, order and recovery parity broker by broker; migrate only verified accounts to explicitly approved native routing; retire auto-rsa's *specific* responsibilities as their native replacements reach production quality. Achieve eventual zero auto-rsa runtime dependence without an all-or-nothing rewrite.

## Current verified/reported boundaries

- `rsassistant/services/broker_protocol.py`, `rsassistant/workers/broker_bridge.py` implement typed worker with feature flag off.
- Existing `rsassistant/integrations/brokers/snapshot.py` is legacy JSON read-only shadow, **not live native parity**.
- Reported parity Fidelity 114/114, Fennel 110/110, Public 114/114, Robinhood 185/185, Vanguard 5/5, Wells Fargo 17/17 is parity of snapshots vs SQL, not of new independent brokerage clients.
- Historical `rsa_order_send_log` has unknown fills; Fidelity 176 ambiguous confirmation logs and Public Sept 29 liquidation outcome require broker-native order/activity evidence.
- Operator reports local commits through `39c0e5b`, Restic not yet installed, pending production deployment and safe liquidate default; do not assume complete or deployed.

## Work steps

1. **Readiness inventory.** Verify reviewed versions of native registry, broker adapters, event/account identity, execution hold, Restic backup+restore, safe deploy and explicit live trading authorization. Verify per-broker license and provider ToS/security feasibility; missing official endpoints remain UNSUPPORTED.
2. **Read-only parity.** On same independently verified broker session compare accounts, positions (completeness/timestamps/Decimal), orders and activities, cash corporate actions, and freshness across independent native vs legacy sources. File redacted discrepancy reports in secure operator store; no account IDs/secrets in repository.
3. **Recovery rehearsal.** Simulate expired sessions, 429 Retry-After, missing driver, device approval, partial positions, inconsistent account aliases, network timeouts. Confirm a login profile's ambiguous-execution hold blocks **all** native/legacy/queued/command order submission paths, while read-only reconciliation continues.
4. **Order-state parity.** Confirm order-intent and broker-order IDs are distinct; broker confirmed fill only from broker activities/executions. Zero replay from historical sends; the adapter selector must never retry unknown native submit via legacy. Preserve historical intent audit.
5. **Per-broker route and canary.** Promote with explicit operator approval and account-scoped preview/limits only after documentation and separate approval for any *actual* orders. Route one broker/account at a time; rollback uses pinned legacy worker but cannot re-send unresolved orders.
6. **Upstream retirement proof.** For each migrated broker, remove old `!rsa` transmit/regex reply and JSON snapshot importer dependency for that broker; confirm no cron/scheduler/GUI path reactivates the legacy bot. Leave isolated fallback only for brokers still documented as unmigrated.
7. **Cutover report.** Output matrix listing broker/profile, supported operations, authentic data sources, reconciliation coverage, open defects, version pin, native/live mode, rollback outcome and human signoff. Flag `zero_upstream_runtime_dependency` TRUE only when **every required active broker** has exited the legacy path.

## Gate conditions

- **HUMAN REFRESH BEFORE IMPLEMENTATION:** Broker choice/priority, physical local storage/backups, real authenticated session and provider access required. Current GitHub main does not contain reported local five commits; reconcile first.
- **HUMAN AUTHORIZATION BEFORE LIVE CANARY:** No production rebuild or trade without user's explicit separate approval, safety flags, verified Restic and checkpoint backups.
- **STOP** if any required broker fills remain unknown, current positions stale, untested MFA/code storage, older RPC lacks idempotency/hold enforcement, or rollback could duplicate a trade.

## Tests / validation

- `python -m unittest discover -s unittests -p '*_test.py'` and `python -m compileall -q rsassistant utils scripts unittests` after code integration.
- Focused broker native fixtures: duplicate intents on crash/restart, lost ack, explicit rejected 429, timeout unknown, sessions expired, unchanged partial scan, cross-account mapping collisions.
- `python scripts/broker_shadow_parity.py --broker fidelity` and for each relevant broker; **supplement** with a second independent broker-session acquisition, not solely existing JSON-to-SQL comparison.
- Protected real DB restore test, per-broker read-only production smoke and user-approved canary only where allowed.

## Acceptance criteria

- [ ] Every native-routed broker has independently fetched fresh account/position parity and actual order/activity source.
- [ ] Legacy Discord order relay and output parser unused for that broker; no shared snapshot import as native authority.
- [ ] No unknown order replicated during cutover or rollback.
- [ ] Explicit operator-approved promotion and rollback evidence per broker.
- [ ] Unsupported broker stays disabled or pinned isolated legacy source, not fabricated native capability.
- [ ] Human-reviewed licensing/third-party provenance; secret-free diagnostic artifact policy.
- [ ] All test and runtime limits recorded; live acceptance evidence separated from mocks.

## Non-goals

No all-16-broker mandate, no automatic production deployment, no automatic trading canary, no GPL source copying, no rewriting external official broker APIs, no assertion that a separate worker eliminates GPL duties.

## Completion report

When implemented and verified, write `docs/task-packets/summaries/TP-20261016-018-SUMMARY.md`, update canonical TRACKER/INDEX and move to completed. Success can be **partial at product level** if some optional brokers remain in isolated compatibility mode; explicitly retain the not-yet-eliminated dependency in status and do not mark `zero_upstream_runtime_dependency` until proven. Next execution step is TP-016's human cutover review.
