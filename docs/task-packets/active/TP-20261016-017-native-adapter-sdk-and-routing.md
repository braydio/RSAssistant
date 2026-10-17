# TP-20261016-017: Native brokerage adapter SDK, capability registry and safe routing

**Packet ID:** TP-20261016-017
**Status:** Draft
**Created:** 2026-10-16
**Last updated:** 2026-10-16
**Repository:** braydio/RSAssistant
**Target branch:** main, after local branch reconciliation
**Canonical path:** `docs/task-packets/active/TP-20261016-017-native-adapter-sdk-and-routing.md`
**Workstream size:** One foundational, independently testable implementation packet
**Priority:** P0
**Depends on:** TP-20261016-004, -005, -006, -008 (Complete); TP-002 safety integration; TP-007 recovery contract
**Execution order:** AFTER TP-008 / BEFORE TP-009 (numeric ID assigned after the original 16-packet train; do not confuse creation ID with execution order)
**Authoring chat:** not-recorded

## Objective

Own and implement the **RSAssistant-native BrokerAdapter SDK and adapter registry**, completely separate from auto-rsa imports, using the current typed IPC contract. Add an explicit per-broker read/write capability matrix and a fail-closed legacy compatibility selector. This is **not** permission to log into brokerages or place trades.

## Current known code (GitHub main `7db0012`)

- `rsassistant/services/broker_protocol.py`: `Operation` enum (LIST_ACCOUNTS, POSITIONS, GET_ORDER, ACTIVITIES, SUBMIT_ORDER, CANCEL_ORDER, HEALTH); Request/Response, PROTOCOL_VERSION=1, mutating ops require idempotency key.
- `rsassistant/workers/broker_bridge.py`: versioned Unix-socket worker; already shadow-only / submission-disabled under `RSA_BROKER_BRIDGE_ENABLED=false` in `config/.env.example`.
- `rsassistant/integrations/brokers/snapshot.py::SnapshotBrokerAdapter`: read-only snapshot adapter supporting list_accounts, positions, health only; **not** live brokerage execution.
- `rsassistant/integrations/brokers/fidelity/adapter.py`: snapshot-backed Fidelity wrapper. `PROVENANCE.md` records auto-rsa 110439c, GPL; no source copied.
- `rsassistant/services/broker_health.py`, `broker_recovery.py`, `rsassistant/persistence/account_identity.py` and `order_intents.py` (verify current main after operator's later unpushed `39c0e5b`).
- `auto-rsa/` nested checkout is **not a native dependency target**. Legacy execution may remain pinned and separated until migration.

## Required implementation

### A. SDK and types (new files)
- `rsassistant/integrations/brokers/base.py`: `NativeBrokerAdapter` Protocol (async or worker-safe sync consistent with current bridge; evaluate bridge loop) with `capabilities`, `health`, `list_accounts`, `get_positions`, `get_order`, `get_activities`, `submit_order`, `cancel_order`, `recover_session`. No Discord types or DB handles in adapter signature. Reuse `Operation` and Request/Response, never create a parallel wire schema.
- `rsassistant/integrations/brokers/models.py`: typed AccountInfo/Position/OrderReceipt/ExecutionActivity/HealthInfo models; UTC timestamps and `Decimal` serialized as decimal strings; complete/partial scan; `source_id`, `source_type`, `observed_at`, `correlation_id`, `broker_order_id`, `capability`.
- `rsassistant/integrations/brokers/errors.py`: stable error categories mapped onto `broker_protocol.ErrorClass` and health incident classes; distinguish `RateLimited(retry_after)`, `ReauthRequired`, `BrowserFailure`, `BrokerUnavailable`, `UnsupportedCapability`, `AmbiguousOrderOutcome`. No catch-all that reports success.
- `rsassistant/integrations/brokers/registry.py`: read-only source/capability and license metadata per broker: `native`, `legacy`, `snapshot_shadow`, `disabled`; selection is explicit per broker/login profile, guarded feature flag default legacy; when native capability absent, return UNSUPPORTED or *explicitly permitted* legacy fallback only, never silently reroute mutating orders.

### B. Authority boundaries
- Broker adapter only gathers broker-originated facts or submits one authorized intent; it cannot directly update canonical SQLite. Domain services in `rsassistant/persistence/orders.py`, `rsassistant/persistence/account_identity.py` own persistence and reconciliation.
- Pre-dispatch guard must check: per-login circuit breaker / ambiguous-execution hold; broker capability; target account alias verified; live-mode explicit approval; write-ahead immutable idempotency key; rate limit. On an unacknowledged submit, mark UNKNOWN, require broker-order-history reconciliation, **never retry** by switching from native to legacy.
- A compatibility adapter may **invoke isolated version-pinned auto-rsa** for authorized unmigrated brokers over typed IPC only; preserve GPL notice and keep credential/session data inside worker. No source copying or direct imports into MIT tree. Compatibility must be human-reviewed for licensing before distribution.

### C. Validation and provenance
- `docs/broker-capabilities.md` (new): each broker/login capability, source mechanism (official API/SDK/browser/legacy), evidence date, terms/licensing reviewed flag, last validated adapter/driver versions, open restrictions.
- `unittests/native_broker_registry_test.py` (new): malformed/unknown broker, unsupported op, profile misrouting, disabled default, fallback fail-closed, mixed capabilities, protocol mismatch, source provenance and redacted diagnostic errors.
- `unittests/native_broker_contract_test.py` (new): Decimal precision, UTC time zone, missing positions partial flag, unknown fill vs accepted, duplicate idempotency key, crash-before/after send, no DB access from worker, rate limit no send, auth challenge needs user.

## Implementation order

1. Read current TP-008 summary and confirm merged protocol, bridge and snapshot symbols (no repo-wide rediscovery unless stale).
2. Introduce types, errors and capability registry; keep `RSA_BROKER_BRIDGE_ENABLED=false` and `native_submissions_enabled=false` defaults.
3. Add compatibility source selector and mock native adapter, read-only only; preserve old production command path.
4. Wire typed health and profile hold into adapter invocation contract, not live trade routing.
5. Add fixtures/tests; run focused + existing full suite on scratch DB. Confirm zero tests contact brokerage network or import auto-rsa.
6. Update `docs/architecture.md`, `config/.env.example` only if adding keys; update tracker and summary upon actual completion.

## Required refresh gate

**STOP before Ready** until the owner-reported five unpushed commits are reconciled; verify which code already handles per-profile hold, Restic, deployment flags, recovery UI. Respect live TP-002/007 gates. No live browser session required for this foundation packet.

## Acceptance criteria

- [ ] Single owned, typed SDK/registry used by mock native adapter; no auto-rsa imports.
- [ ] Snapshot adapter retained as truthful read-only fixture, not presented as live broker API.
- [ ] No unsupported or unknown capability routes orders to a different client implicitly.
- [ ] Decimal, timestamps, completeness, account identity and evidence provenance normalized and tested.
- [ ] Unknown execution cannot be retried across adapters or fallbacks.
- [ ] All actual Python tests compile and pass on disposable DB; failures recorded.
- [ ] No live orders, deployment or account login.

## Non-goals

No Fidelity or other broker live implementation; no rewriting all auto-rsa scripts; no brokerage login data in fixtures; no removal of the separate GPL worker; no live trade canary. No new independent HTTP trading API service.

## Completion report

Write `docs/task-packets/summaries/TP-20261016-017-SUMMARY.md` with Outcome / Validation / Process Feedback / Next Handoff; move canonical file and update INDEX and TRACKER only when implemented. **Next execution packet: TP-20261016-009**, after its own live-session and order-reconciliation refresh gates.
