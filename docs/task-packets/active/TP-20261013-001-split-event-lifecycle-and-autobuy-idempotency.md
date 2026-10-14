# TP-20261013-001: Split Event Lifecycle + Autobuy Idempotency

**Packet ID:** TP-20261013-001  
**Status:** Ready  
**Created:** 2026-10-13  
**Last updated:** 2026-10-13  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261013-001-split-event-lifecycle-and-autobuy-idempotency.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-005 (Complete); coordinate with Draft TP-20261010-011  
**Priority:** High  
**Authoring chat:** not-recorded  
**Expected packet count / order:** Two independent audit findings, TP-20261013-001 and TP-20261013-002; run 001 first due to trading-state correctness, then 002 or any existing priority work.  


## Objective

Prevent **premature loss of active reverse-split sell tracking** and **duplicate/replayed automatic buy scheduling** from the same corporate action, while preserving legitimate new split events for a ticker on a different effective date. Treat trade intent submission, Discord send, brokerage execution and confirmed holdings as different states. No new trading strategy or increased trading frequency.

## Confirmed current code (main, static audit 2026-10-13)

- `utils/split_watch_utils.py::cleanup_expired_tickers()` removes **any** `split_monitor` entry with `split_date < today`, regardless of buying/selling status or `accounts_bought` versus `accounts_sold`:
  ```python
  if split_dt is not None and split_dt < today:
      expired.append(ticker)
  # DELETE FROM split_monitor WHERE ticker=?
  ```
  `rsassistant/bot/cogs/split_monitor.py::split_status()` invokes this cleanup before reading status, while `split_cleanup()` invokes `update_split_status()` and `cleanup_completed_tickers()`. Consequently an open selling-phase watch can disappear simply because an operator requests status. Existing `unittests/split_watch_utils_test.py::test_expired_cleanup_removes_only_past_iso_dates` **expects deletion**, so update it rather than leaving a failing/incorrect historical assertion.
- `rsassistant/bot/handlers/on_message.py::handle_secondary_channel()` passes confirmed round-ups to `_process_round_up_flow()`; that reads `get_status(ticker)`, then separately runs `add_split_watch` and `attempt_autobuy`. This is check-then-act around the persistence boundary. Two close incoming alerts can both observe a missing watch and both schedule buys. Once an expired watch is removed, a replay can trigger new buys.
- `utils/split_watch_utils.py::add_split_watch()` uses `INSERT OR IGNORE` into `split_monitor` but returns no durable "newly claimed event" outcome. `split_monitor` is currently keyed by **ticker only** in `rsassistant/persistence/schema.py::_migration_6` (or exact current migration function; inspect same local schema block); `split_monitor_accounts` cascade-deletes account status.
- `rsassistant/bot/handlers/on_message.py::attempt_autobuy()` creates a new UUID for each standard/broker-override order and calls `bot.loop.create_task(schedule_and_execute(...))`. No shared claim ties an alert's (ticker, split_date) to those UUIDs.
- `utils/order_exec.py::schedule_and_execute()` uses SQLite order queue and `send_sell_command`; `utils/order_queue_manager.py` owns queue persistence. `rsassistant/bot/tasks.py` reschedules queued orders. Timer consolidation belongs to existing **Draft TP-20261010-011**, not this packet.
- `unittests/on_message_roundup_flow_test.py` verifies scheduling a first round-up but not duplicate concurrent alerts, replay after cleanup or same ticker/new date.

## Locked behavior

**Lifecycle:** an active split can transition `buying -> selling -> completed/archived`; **date passage alone must never delete an open selling position**. Keep `cleanup_completed_tickers()` behavior only when a defined completion criterion holds, and require bought accounts to be matched by sold accounts. Missing account confirmations means "needs attention", not automatically sold. Preserve ability to explicitly remove a watch using the existing operator command/function; its action must not erase the durable corporate-action history.

**Identity:** An actionable corporate event is identified by normalized `(ticker, effective_date)`, not ticker alone, source Discord message ID alone, or a mutable watchlist row. Different alerts/filings referring to the *same* event must not create new auto orders. A genuinely separate later split of the same ticker is not forever blocked by historical records. Reject absent, malformed and unreasonably stale/effective dates for automatic order scheduling; **never default a missing effective date to today for auto trading**. Keep ambiguous policy or timing in review-only state without scheduling an order.

**Exactly-once claim, not exactly-once external fill:** Add durable transactional uniqueness for the **intent/dispatch plan** using SQLite, not an in-memory set. A Discord send is not an execution/fill confirmation. In an unknown send or crash window, mark the intent `needs_reconciliation` and do not blindly reissue an order on restart. Existing order scheduler/queue remains the only owner of scheduled execution.

## Required files and design

### 1. `rsassistant/persistence/schema.py` and `rsassistant/persistence/reverse_splits.py` (or focused split monitor persistence in `utils/split_watch_utils.py`)

Append a new `PRAGMA user_version` migration (currently `LATEST_SCHEMA_VERSION=9`, so use 10 if still current). Preserve `split_monitor` and `split_monitor_accounts` and all existing persisted rows. Introduce **separate durable event identity/intent records** instead of rekeying the existing ticker-PK watch table prematurely.

Proposed tables:
```sql
CREATE TABLE split_event_intents (
  ticker TEXT NOT NULL,
  split_date TEXT NOT NULL,
  source_ref TEXT,
  state TEXT NOT NULL CHECK(state IN
    ('claimed','planned','submitted','needs_reconciliation','suppressed')),
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_reason TEXT,
  PRIMARY KEY(ticker, split_date)
);
CREATE TABLE split_event_order_intents (
  ticker TEXT NOT NULL,
  split_date TEXT NOT NULL,
  dispatch_key TEXT NOT NULL,
  order_id TEXT,
  state TEXT NOT NULL CHECK(state IN
    ('planned','queued','submitted','needs_reconciliation')),
  last_error TEXT,
  PRIMARY KEY(ticker, split_date, dispatch_key),
  FOREIGN KEY(ticker, split_date) REFERENCES split_event_intents(ticker, split_date)
);
CREATE UNIQUE INDEX uq_split_event_order_id
ON split_event_order_intents(order_id) WHERE order_id IS NOT NULL;
```

Proposed API:
```python
claim_split_event(ticker: str, split_date: str, source_ref: str|None) -> ClaimResult
record_split_order_plan(ticker, split_date, order_specs_with_stable_dispatch_keys) -> ...
mark_split_order_queued(ticker, split_date, dispatch_key, order_id) -> ...
mark_split_event_needs_reconciliation(ticker, split_date, reason) -> ...
```
Use `BEGIN IMMEDIATE`, `INSERT ... ON CONFLICT DO NOTHING`, commit/rollback correctly, and return `claimed | already_claimed | invalid | requires_review`. Do not select then insert without a transaction. Keep `source_ref` safe, bounded, and non-authoritative. The table records **intent**, not brokerage acknowledgment. For a process crash between durable claim and execution, retain the claim and require operator reconciliation; do not silently auto-retry.

### 2. `utils/split_watch_utils.py`: fix phase-safe cleanup and compatibility

- `cleanup_expired_tickers()` must not delete active buying/selling watches solely for age. Preserve callable signature/return type for existing callers; it may delete only definitively completed entries, or delegate to the same completion predicate as `cleanup_completed_tickers`. Distinguish active overdue in return/status rather than erase it.
- `cleanup_completed_tickers()` should have a single conservative completion predicate: status selling, at least one recorded bought account, and **all bought account identities marked sold** (not just equality that rejects harmless extra sold markings); ensure no pending order intent is being mistaken for a filled/sold account.
- `add_split_watch`, `get_status`, `get_full_watchlist`, `update_split_status`, `mark_account_bought/sold`, `remove_split_watch` retain existing public dict shapes. Don't reset a different-date **active** ticker automatically.
- Make an explicit operator-accessible review/replace path for same ticker with a later split date; preserve the old corporate-action intent record and do not carry over old account bought/sold markers.

### 3. `rsassistant/bot/handlers/on_message.py`: update processing boundary

- In `handle_secondary_channel`, do not use `date.today()` fallback for an **actionable** split date. Missing/ambiguous date posts a source/policy summary marked "manual verification required" but triggers **zero** buy schedules.
- In `_process_round_up_flow`, normalize/validate event identity and acquire the durable claim **before** altering watchlist or invoking `attempt_autobuy`. On duplicate claim: post concise already-tracked status (with date) and do not schedule.
- Preserve `post_policy_summary`, manual watchlist updates and channel-routing behavior; do not silently change parser precedence or buy strategy.
- Build all broker-specific order plans from existing `rsassistant/services/order_orchestration.py::build_autobuy_orders` before scheduling; persist an intent row per distinct broker override/standard plan with a stable dispatch key. If a broker plan or scheduling call fails, set unresolved state. Don't call `attempt_autobuy` twice under concurrent alerts.
- Do not equate a successfully enqueued task/Discord send with filled shares. Avoid autopopulating `accounts_bought` until real holdings/order evidence confirms that account.

### 4. `rsassistant/bot/cogs/split_monitor.py`: operational visibility

- `splitstatus` and `splitlist` should show phase (buying, selling, overdue, reconciliation needed) without deleting active items as a side effect. Calls remain read-only except harmless explicitly documented migration compatibility.
- `splitcleanup` transitions due entries to selling and archives **only proven-complete** watches. Include counts for transitioned, completed, still open, and needs attention.
- Add the smallest operator-only "review unresolved split intent" affordance using existing command style or extend current `splitstatus`; avoid exposing raw account identifiers unnecessarily.

## Test plan

Add `unittests/split_event_intents_test.py` (SQLite with temp DB), extend `unittests/split_watch_utils_test.py`, `unittests/on_message_roundup_flow_test.py`, `unittests/split_monitor_test.py`. Mock all network, Discord sends, broker responses.

- A past-date `selling` entry with bought A and unsold A survives `splitstatus`/cleanup; fully sold A archives.
- Same (ticker,date) concurrent claims return exactly one winner, including across separate DB connections/process contexts; first intent's broker plans persisted once.
- Duplicate same-day and delayed replay after watch archive: **zero** duplicate autobuy schedules; different later effective date is independently claimable once.
- Unknown/missing effective date or unsupported policy: **zero** autobuys and explicit review status.
- Existing active ticker, different upcoming date: no auto replacement until operator resolves identity; old account marks preserved.
- Broker standard + override intents unique, no send/queue duplication across retries; crash/timeout after claim requires reconciliation and no automatic duplicate resend.
- `split_status`, `split_orders`, `split_cleanup` remain compatible; valid manual watch flow unaffected.
- SQLite v9 -> v10 migration preserves all watch/account/order rows, and repeated migration is idempotent.

Focused:
```bash
python -m unittest unittests.split_event_intents_test unittests.split_watch_utils_test unittests.on_message_roundup_flow_test unittests.split_monitor_test
python -m unittest discover -s unittests -p '*_test.py'
python -m compileall -q rsassistant utils unittests
```

## Implementation order

1. Validate this packet's named seams against current main and TP-20261003-005 schema contract; mark packet/tracker In Progress.
2. Schema migration + atomic claim repository + tests. No destructive migration/replacement of active watchlist PK.
3. Phase-safe cleanup + status API tests.
4. Hook claim and per-broker intent planning into round-up flow; mock concurrent messages.
5. Commands/reporting, docs `docs/architecture.md` and `README.md` operator notes, run focused/full tests and record deviations.
6. Create `docs/task-packets/summaries/TP-20261013-001-SUMMARY.md`; archive packet to completed with index/tracker atomically if actually verified.

**Do not rediscover:** TP-20261010-011 owns timer consolidation; TP-20261010-004 owns holdings import retries; TP-20261010-002/003 own async scheduling/nonblocking networking. This packet changes **split lifecycle and duplicate automated trade intent**, not the execution scheduler.

## Non-goals

No new buy strategy, automatic additional trades, broker-account allocation change, trade fill guarantees, market holiday changes, replacing SQLite, deletion of historical event/audit rows, or generalized trading P&L calculations.

## Acceptance criteria

- [ ] A past-date split with any unsold bought account remains tracked and visible.
- [ ] The same ticker+effective-date alert, including concurrent or delayed replay, cannot schedule another autobuy without explicit operator reconciliation.
- [ ] Different legitimate split events for one ticker are representable without erasing prior status.
- [ ] Invalid/absent dates fail closed to review-only; no implicit today's-date automatic trading.
- [ ] DB migration idempotent with preserved historical/watch/order state and safe crash behavior.
- [ ] Commands reflect actual phase without deleting open work; explicit status after unresolved dispatch.
- [ ] Automated regression tests pass, or exact preexisting blockers are stated.

## Completion report

Report **PACKET COMPLETE** only when done. Give status, commit URL, persistent summary path, exact focused/full tests, migration/runtime compatibility, whether production data migration was performed (never assume), any manual-reconciliation items, and next packet: TP-20261013-002 or existing highest-priority Ready packet. Authoring chat: not-recorded.

