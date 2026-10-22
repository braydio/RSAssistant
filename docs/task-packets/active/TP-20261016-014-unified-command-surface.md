# TP-20261016-014: Replace scattered commands with one typed operator interface

**Packet ID:** TP-20261016-014  
**Status:** In Progress
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-014-unified-command-surface.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P1  
**Depends on:** TP-20261016-008, -012, -013  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-014 is #14; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Replace scattered commands with one typed operator interface. This is a scoped executable brief **only after refreshing from Draft to Ready** and verifying the dependencies; writing this packet does not authorize any live trading or deployment.

## Current evidence and source boundary
Current about 39 prefix commands spread over ten cogs, plus ULT-MA commands and separate !rsa bot. Overlap among watchlists/split monitors, order queue/history, ownership and performance.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These are distinct baselines. Local-only broker forks/patches must be preserved.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: API shape, permissions and reconciliation semantics must be stable; review current main command list incl local splitreview/splitresolve/splitreplace/watcherstatus. Do not remove old aliases until telemetry and compatibility review.**

The implementer must read dependency completion summaries, compare the named source paths and symbols against *then-current* main, and revise stale details in this canonical packet before marking `Ready` and then `In Progress` in both `TRACKER.md` and `INDEX.md`. Unresolved technical or human gates mean **Blocked**, not implicit authorization.

## Exact files and contract anchors
- `rsassistant/bot/core.py`
- `rsassistant/bot/cogs/orders.py`
- `rsassistant/bot/cogs/holdings.py`
- `rsassistant/bot/cogs/split_monitor.py`
- `rsassistant/bot/cogs/accounts.py`
- `rsassistant/bot/cogs/watchlist.py`
- `rsassistant/bot/cogs/reporting.py`
- `rsassistant/bot/cogs/performance.py`
- `rsassistant/bot/cogs/admin.py`
- `rsassistant/services/ (query facade)`
- `unittests/command_contract_test.py (new)`

## Required changes / implementation order
1. Create app_commands Discord slash tree: /rs status; /rs splits list/show/review/approve; /rs portfolio accounts/holdings/refresh/history; /rs orders list/show/reconcile/cancel; /rs trade preview/buy/sell; /rs reports pnl/roundups/performance; /rs system health/jobs/config.
2. Commands call typed application services only; no direct SQLite writes, file edits or Discord-to-Discord order messages inside handlers. Application services are UI-agnostic for later local dashboard.
3. Group interactions into paginated embeds with account-safe redaction and evidence links, output statuses UNKNOWN, STALE, PENDING explicitly. Trade actions require permission check, preview+confirmation, amounts and account scope.
4. Preserve old prefix commands as read-only redirects or explicitly mapped compatibility aliases during transition; collect deprecation telemetry and identify commands with live order side effects.
5. Move owner/admin maintenance commands to protected ops layer, remove `..patchautorsa`/runtime Git pull triggers after deployment safety is ready. Keep ULT-MA isolated and disabled by default.

## Cross-packet invariants
- Corporate action identity is `(ticker,effective_date)`, not mutable watchlist ticker alone; preserve durable TP-20261013-001 intent claims.
- Command submitted, broker accepted and execution filled are different states. Unknown outcome means pause and reconcile, **never blind retry**.
- SQLite owns canonical runtime state; JSON/CSV only staged input, export or historical evidence.
- All tests must use disposable temporary databases and broker mocks. Healthcheck and backfill must never place live orders.
- Every adaptation retains original source license/provenance and any unique locally uncommitted GUI code.
- Live open split watches, account mappings, history and broker evidence must not be deleted by cleanup/status commands.
- New migrations must be additive/restart-safe with restore checkpoint and idempotent backfill, recording outcome in summary.

## Tests / exact validation
- `python -m unittest unittests.command_contract_test unittests.discord_permissions_test unittests.command_error_handler_test`
- `permissions operator vs viewer; no live trades on read-only commands; alias equivalence; pagination; stale positions`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Record read-only parity evidence with timestamps, source commit, account counts and explicit unknowns; separately name tests not runnable without local broker environment.

## Acceptance criteria
- [ ] One discoverable /rs command tree covers normal workflows
- [ ] No privileged state change possible through a read-only alias
- [ ] Every displayed order/position has freshness and evidence status
- [ ] Old aliases can be rolled back without losing events
- [ ] Existing trade idempotency, pending orders and historical records preserved.
- [ ] Mandatory refresh/human gates are satisfied and recorded in tracker.
- [ ] Focused/full tests and any migration/rollback commands logged in durable closeout.

## Non-goals
No UI-controlled implicit autobuys, no arbitrary SQL execution, no public API exposure.

## Completion report and successor
On verified completion: move only this packet to `docs/task-packets/completed/`; update `INDEX.md` and `TRACKER.md` atomically; write `docs/task-packets/summaries/TP-20261016-014-SUMMARY.md` in required Outcome / Validation / Process Feedback / Next Handoff format. Next packet: TP-20261016-015. State whether refreshed planning/owner review is required, and **do not** claim broker/live parity based on mocks alone.

## Scoped early deliverable: reverse-split holders lookup (2026-10-22 amendment)

**Owner-approved functionality:** Add a read-only bot command that immediately answers "which of my brokerage accounts already hold this potential upcoming reverse split, what quantities, and which accounts do not?" This deliverable is explicitly part of TP-014 and **may be implemented and tested independently before the full slash-command consolidation and TP-013**. Do not wait for native broker adapters: canonical SQLite holdings is sufficient for a carefully labeled current-snapshot view.

### Operator commands and compatibility

- Prefix: `..splitholders <ticker> [broker]`; choose unique alias `..sholders` only after checking `docs/command-inventory.md` and actual registered Discord command names.
- Future native slash equivalent: `/rs splits holders ticker:<symbol> broker:<optional>`.
- Both call **one shared read-only application query function**; no SQL, refresh, scheduling, broker IPC, account changes, or orders from the Discord handler.
- Keep `..brokerwith`, `..splitstatus`, `..splitlist`, `..splitorders` and existing aliases unchanged. This command aggregates their relevant *facts*, without representing a historical buy marker as a current holding.
- Invalid ticker: a helpful validation message; ticker not on watchlist: show current holdings but clearly label "no watched split", with no assumed ratio/date. Multiple events for same ticker must resolve by event/effective date (when available), never reclassify a former split as the upcoming one.

### Data contracts and query path

1. Add `rsassistant/services/split_holders_query.py` (new, actual module name subject to current main refresh) providing a typed, independently testable `get_split_holders(ticker, broker=None, *, database=...)` read-model. Query `rsassistant/persistence/holdings.py::get_current_holdings` / `holdings_current` on **one read-only SQLite snapshot**; do not trigger `import_holdings_if_updated` or `!rsa holdings` by default.
2. Join **without duplicating**: `Accounts`, `canonical_accounts`, `account_canonical_map`, `account_aliases`, verified login/group identity where available; normalize broker spelling, account nickname and ticker. Aggregate exact quantities as `Decimal` per stable canonical account + broker login profile and symbol. If alias mapping is ambiguous, display that account as unresolved, not a zero position or a second account. Never group by last-four alone.
3. Build denominator from the **verified account roster** (including accounts with zero positions) instead of relying on `holdings_current` to enumerate all accounts; where broker scan is incomplete, distinguish `NOT_HELD` (authoritatively complete) from `UNKNOWN` (no evidence), `STALE` (old timestamp), and `IDENTITY_UNVERIFIED`. Missing rows do not prove zero; negative/short quantities are not a positive holding. Surface each broker/profile's latest successful snapshot and completeness. Use current `holdings_import_log` / broker health metadata where available; label unsupported granularity explicitly.
4. Join the `(ticker,effective_date)` split watch and policy-evidence record **read-only**. Present announced ratio, market effective date, split phase, source link, document/verification time and policy classification: `ROUND_UP_UNCONDITIONAL`, `ROUND_TO_NEAREST`, `CASH_IN_LIEU`, `AGGREGATED_PARTICIPANT`, `CONFLICT` or `UNKNOWN`. Conflicting or outdated filings display "review required", never "round-up confirmed". DTC-participant-level rounding must not imply individual account credit.
5. Display durable event intent/status/actual broker fills only as separate fields: `watch-marked bought`, `order sent/unknown`, `broker fill verified`, `current holding`. Never confuse these. Upcoming/previous event date is explicit, and prior watched events are retained.

### Discord output design

- Compact summary: `TICKER | ratio | date | evidence status | watched phase`, `holding_accounts / known_roster`, `total positive pre-split shares`, `snapshot_at`, `unknown/stale counts`.
- Grouped by broker, then account: **operator-facing nickname + masked last four, login-profile label, positive share quantity, source timestamp**. If no holdings, output `none confirmed / missing data` accurately.
- Optional `[broker]` filter without changing totals for other brokers; `--all` or future UI toggle to include not-holding and unknown accounts when Discord embeds are crowded.
- If the ratio is verified, optionally show an **illustrative** Decimal `pre_qty / ratio` post-split quantity; never apply a ceiling unless the shareholder-level rounding provision and relevant broker processing are actually evidenced. Do not label projected shares as credited, and do not silently fabricate execution value or fees.
- paginate to Discord limits, never log full account identifiers or credentials; default to operator-only for account-level breakdown and permitted read-only summary for authorized viewers. Avoid public-channel disclosure of sensitive portfolio information.

### Implementation order and exact anchors

1. **REFRESH GATE:** inspect the current local main (reported deployed `f97d0b7` earlier and subsequently unpushed local work) rather than remote GitHub `7db0012`; inspect `rsassistant/bot/cogs/reporting.py::broker_has`, `utils/utility_utils.py::track_ticker_summary`, `rsassistant/bot/cogs/split_monitor.py::split_status`, `rsassistant/persistence/holdings.py::get_current_holdings`, `rsassistant/persistence/account_identity.py`, `account_verification.py`, current `split_policy_evidence`, and command registration. Reuse rather than fork calculation helpers.
2. Implement pure selector/formatter + readonly database query service with `Decimal`, explicit status/time and source contract. No schema migration for this phase unless evidence demands one, with separate refresh gate if needed.
3. Add `splitholders` prefix command to existing ReportingCog (or dedicated split cog after inspecting actual current code); use async thread offload for SQL if applicable. Build paginated embeds, permission checks and optional broker filter.
4. Add `/rs splits holders` route later when the TP-014 app_commands group becomes available; do not block the early prefix command for full command reorganization.
5. Maintain command inventory, help text and link to existing `..brokerwith`/ `..splitstatus`; update a focused progress section but do not mark TP-014 Complete until its other command-surface acceptance criteria are satisfied.

### Focused validation / acceptance

- `unittests/split_holders_query_test.py` (new) and relevant cog command tests; execute with `.venv/bin/python`, scratch `VOLUMES_DIR`, disposable DB.
- Holdings present in two brokerages and multiple accounts: totals and groups exact; equivalent ticker spelling; duplicate aliases not double-counted; multi-account same last-four stays separate.
- Some roster accounts have zero holdings, some snapshots are partial/stale, some accounts are unverified, some negative quantities: no false "not held" and no incorrect eligible-account counts.
- Split watched vs not watched, multiple distinct split dates per ticker, missing/conflicting rounding policy, DTC-only rounding: no invented shareholder round-up confirmation.
- Existing durable watched buying accounts or Discord send logs **do not** count as current holdings or broker fills.
- Verify unauthorized account-level requests fail, Discord embed pagination does not truncate accounts silently, and **zero calls** to order dispatcher, scheduled jobs, live broker APIs, holdings refresh and any mutating database method.
- Run focused and full unittest suites, compileall, record baseline pytest discrepancies separately. **No trade execution, watch modification, autobuy scheduling or deployment** in this packet amendment.

**Definition of done for this slice:** The operator can execute `..splitholders TICKER` against an existing complete enough SQLite snapshot and immediately see exactly which known accounts hold positive quantities, which are confirmed empty and which cannot be classified, while viewing current split terms with explicit evidence/conflict status. Treat this slice as separately delivered within an otherwise In Progress TP-014.

## Progress log (2026-10-16)
Done (read-only audit, no command changed or removed): `scripts/command_inventory.py` + generated `docs/command-inventory.md` — 40 commands from the cog sources via AST. Authorization audit: every trade/destructive command (`order`, `liquidate`, `remove`, `queue_run`, `restart`, `shutdown`, `patchautorsa`, `clear*`, `split*` mutators, etc.) carries a decorator check (`admin_only` or `has_permissions`); the 15 commands with no decorator are read-only reporting (`aliases, all, brokerlist, brokerwith, grouplist, history, lastorder, orders, ownersummary, performance, queue, splitlist, splitstatus, top, watchlist`). Note `queue` (list) is unchecked while `queue_run` is checked — verify intent.
**Remaining (gated on a stable API + telemetry):** typed operator interface, alias retention, any removal. Status stays In Progress.
