# Native brokerage integration strategy (decision lock, 2026-10-16)

**Decision:** RSAssistant owns its brokerage interfaces, account/session lifecycle, order-intent lifecycle, execution evidence, recovery and data contracts. The NelsonDane auto-rsa fork is a **pinned, temporary compatibility implementation**, not the target architectural dependency. Do **not** rewrite every supported broker at once. Prefer official broker interfaces and appropriately licensed SDKs; maintain independently authored browser/HTTP adapters only where documented interfaces cannot satisfy required capabilities. No representation of an undocumented endpoint as a stable official API.

**Planning status:** Documentation decision only. GitHub base main was `7db0012` when authored; operator reports five local, unpushed commits ending `39c0e5b`, with no deployment. Do not merge this plan by overwriting that local work. No live orders or deploy authorized.

## Desired boundary

```text
/rs command or scheduler -> application service -> canonical SQLite order intent
  -> typed broker router (capabilities / health / per-profile hold / rate limits)
    -> NativeBrokerAdapter [owned code + approved dependencies]
    -> LegacyAutoRsaAdapter [pinned fallback, isolated IPC, NO SQL writes]
       -> upstream/fork legacy execution only while broker still unmigrated
  -> broker receipts / activities / authoritative fills -> reconciliation
```

The already-completed TP-20261016-008 versioned IPC schema is the stable transport boundary, *not* a requirement to implement the adapters as direct imports from auto-rsa. New work must use `rsassistant/services/broker_protocol.py` and `rsassistant/workers/broker_bridge.py`. The existing snapshot adapters are **read-only compatibility fixtures**, not proof that the broker-facing adapter exists or that an order filled.

## Clarifying the term “our own API”

This is a **local RSAssistant adapter API** and optionally a private Unix-socket worker API. It does not mean that we control Fidelity, Robinhood, Fennel, Public or any brokerage's remote endpoints. Remote interfaces and browser flows remain external change risks. Avoid inventing a public HTTP trading server for now.

### Contract matrix

| Operation | Required guarantee | Source |
| --- | --- | --- |
| `health` | Login profile, auth/read/trade capability, timestamp, typed error and incident | Broker session, not JSON mtime alone |
| `list_accounts` | Stable internal UUID and verified account mapping with alias provenance | TP-005 accounts |
| `positions` | Complete/partial/stale marker, observed_at, Decimal quantity | Broker statement/endpoint |
| `order_status` | Broker order ID, timestamp and raw status; unsupported explicit | Brokerage order history |
| `activities` | Executions/corporate actions/cash with distinct authoritative source IDs | Broker activity/statement |
| `submit_order` | Write-ahead claim, exactly one dispatch attempt for each intent, per-account explicit approval and hold check | TP-004/008 |
| `cancel_order` | Request vs broker acknowledgement vs terminal canceled are distinct | Brokerage acknowledgement |
| `reauth` | Protected local user challenge, never OTP through Discord or logs | TP-007 recovery UI |

All business money/quantity values use `Decimal` (serialize as strings, avoid binary float for fills and rounding). Capability registry must indicate `supported`, `unsupported`, `unverified` or `degraded`; do not silently return empty positions after an incomplete fetch. Structured exceptions distinguish transient network, rate limit, auth-required, driver failure, provider change and **unknown order outcome**. Never infer a fill from a successful click, message send or contemporaneous quote.

## Implementation / dependency choices

1. **Official API / supported provider SDK first**, if actually available to the operator and sufficient for account-level portfolios, orders and corporate actions.
2. **Independent native client / browser adapter** built against permitted browser behavior and documented/observed flows, with explicit reliability and terms review, if official functionality is missing.
3. **Narrow approved third-party library** when maintenance, license and security audit are acceptable. Track package name, license, version, API surface, maintenance and breakage risk.
4. **Existing pinned auto-rsa fork** behind a dedicated worker, only as migration/fallback for specific brokers. Do not import GPL source directly into the MIT-licensed RSAssistant tree without a deliberate licensing review and compatible distribution plan.

Separate-process IPC is useful engineering isolation, but **does not guarantee GPL compliance** on its own. Keep provenance, SPDX notices and third-party license inventory. No assumption that a custom clone evades broker ToS, security checkpoints, or requirements for official authorization.

## Order of execution

**Existing 001–008 remain historically completed/in-progress exactly as in tracker.** Add two canonical packets with immutable IDs but insert them at dependency-appropriate positions:

- **TP-20261016-017** (Draft) immediately **after completed TP-008 and before TP-009**: Native BrokerAdapter SDK, capability registry, selection/routing, fixtures, licensing/provenance manifest, legacy fallback shim *read-only*. Any mutating routes default disabled.
- **TP-009 (In Progress)**: Native Fidelity broker implementation. Existing `FidelitySnapshotAdapter` remains a shadow baseline; retained Zendriver/GPL module stays in isolated legacy worker. No code copying. Read-only native live adapter only after session approval; browser automation is an implementation choice, not proof of broker API.
- **TP-010 (In Progress)**: Native Fennel/Public/Robinhood integrations; reuse reviewed third-party SDKs if appropriate, not runtime `auto-rsa` imports. Enforce Fennel Retry-After and ambiguous-execution holds at dispatch boundary.
- **TP-011 (Draft)**: Native Wells Fargo, Schwab, Chase, SoFi, Webull and optional brokers by user priority. Unsupported adapters stay disabled; do not rewrite all 16 merely for parity.
- **TP-20261016-018** (Draft), **after TP-011 and before TP-016**: Native-to-legacy parity and cutover program: per-broker routing flag, verified order/activity/position fidelity, exact source/audit, no legacy Discord command for migrated broker, rollback and licensing signoff. Run after the pre-deployment safety requirements in TP-002 and TP-007.
- **TP-016 (Draft)**: Only retire auto-rsa runtime if **all required actively used accounts have native verified capability** (including order reconciliation), and 018 has closed. Otherwise retain a pinned, isolated legacy worker solely for the remaining explicitly identified brokers and defer complete elimination. The goal is zero upstream runtime dependence, not an unconditional deadline.

Existing TP-012/013/014/015 continue to use canonical services and should not depend on auto-rsa internals.

## Broker sequence and evidence

| Priority | Broker | Native implementation focus | Known evidence/gate |
| --- | --- | --- | --- |
| 1 | Fidelity | Session/positions, order-history/activity and reconciliation before submissions | Snapshot parity 114 positions/21 accounts reported; historical confirmation ambiguity and profile execution hold |
| 2 | Fennel | Rate-limited account/order API, per-login backoff + Retry-After | HTTP 429, new rejection incident and cooling logic reported local-only |
| 3 | Public | Read-only account/positions parity, broker order history, status and partial fills | 94 September 29 live sell commands; reconciliation unresolved for many |
| 4 | Robinhood | Approved SDK client when suitable; normalized orders and positions | Quote HTTP 400 must not block accounting |
| 5 | Wells Fargo | Secure approval, driver/session stability | Phone approval and historical stale sessions |
| Later | Schwab, Chase, SoFi, Webull, Vanguard and any broker actually used | Capability- and need-driven selection | No assumption all 16 brokers need native port; verify owner priorities |

## Gates and release criteria

**Do not deploy merely because new planning packets exist.** Owner still owes approval for deployment window, Restic backup/restore, safe liquidate default/explicit live confirmation, execution-hold enforcement, pin checks and current unittest/pytest results. No new live orders for debugging.

For **each broker**: (a) pinned source/dependency manifest; (b) read-only mock+live session smoke, including auth/freshness and partial scan; (c) account/positions parity against independently fetched broker record; (d) broker order-history and activity reconciliation, no assumed fills; (e) evidence that profile-level hold affects *all* submission paths; (f) offline crash/retry/idempotency and rollback; (g) explicit owner-approved limited trading canary (separately requested), if any; (h) update tracker and durable summary.

Snapshots alone only satisfy (b)/(c). Missing official interface must be called `unsupported` or the implementer must prepare a separate design/terms feasibility review. No bypass of MFA or simulated trades against live accounts.

## Documentation governance and branch integration

Canonical packets: `docs/task-packets/INDEX.md`, `TRACKER.md`, `AGENTS.md`. Historical Complete packet 008 is **not reopened**. Existing packets 009/010/011/016 gain an explicit superseding design amendment but retain their current status and factual progress logs. Packet 017 is authored as Draft, 018 as Draft, and must be refreshed to Ready after their prerequisites.

This plan was prepared on a separate `planning/native-broker-adapters-20261016` branch because the operator reports local commits not yet on `origin/main`. Merge/rebase only after preserving and reconciling them; avoid a second unrelated main commit while that gap remains.
