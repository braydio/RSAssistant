# TP-20261003-005: Move Split Monitor State to SQLite

**Packet ID:** TP-20261003-005  
**Status:** Complete
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261003-005-split-monitor-sqlite.md`
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-003

## Objective

Replace module-global and JSON-authoritative reverse-split monitor state with SQLite while preserving helper APIs and the dictionary shape consumed by Discord handlers and parsing utilities.

## Confirmed current state

- `utils/split_watch_utils.py` loads a process-global `data` object from `volumes/db/split_watchlist.json` and rewrites the whole file on every update.
- `rsassistant/bot/cogs/split_monitor.py`, `utils/parsing_utils.py`, `utils/watch_utils.py`, and `rsassistant/bot/handlers/on_message.py` consume helpers from `utils.split_watch_utils`.
- The handler calls `load_data()` before checking state. Preserve this compatibility function as a database initialization/migration entry point.
- The controller schema requires `split_monitor` and `split_monitor_accounts` with cascade deletion.

## Required changes

### `rsassistant/persistence/schema.py`

Add migration version 6 creating:

- `split_monitor(ticker PRIMARY KEY, split_date, status CHECK status IN ('buying','selling'), created_at, updated_at)`
- `split_monitor_accounts(ticker, account_name, bought, sold, PRIMARY KEY(ticker, account_name), FOREIGN KEY ticker REFERENCES split_monitor ON DELETE CASCADE)`

### `utils/split_watch_utils.py`

Remove the module-global mutable `data` store and all runtime JSON writes. Use `connect_runtime_db()` and the versioned migrations. Keep the existing public APIs:

- `add_split_watch`
- `mark_account_bought`
- `update_split_status`
- `mark_account_sold`
- `cleanup_completed_tickers`
- `cleanup_expired_tickers`
- `get_watchlist`
- `get_status`
- `get_full_watchlist`
- `remove_split_watch`
- `get_all_accounts`
- `load_data` as a compatibility initializer/migration hook

Return each status dictionary with `split_date`, `status`, `accounts_bought`, and `accounts_sold`, preserving account insertion order. Updates must be idempotent and transactionally modify SQL rows.

Import `SPLIT_WATCH_FILE` once: parse and validate the full JSON object before beginning the transaction; import valid tickers and account state idempotently; commit; then rename to `.json.migrated`. Malformed document JSON must remain untouched and raise a clear error. Do not write a new JSON snapshot.

### Tests

Add `unittests/split_watch_utils_test.py` using temporary SQLite and legacy JSON paths. Cover helper return shapes, transitions, idempotent account marking, cascade removal, expiration cleanup, migration/archive behavior, and malformed-source retention.

## Non-goals

- Do not change order-history reads in `SplitMonitorCog.split_orders`; Packet 7 owns that migration.
- Do not change command messages or parsing behavior.
- Do not change the `utils.split_watch_utils` import path in current callers.

## Implementation order

1. Add the schema version 6 migration.
2. Replace split monitor global/JSON state with SQL operations and one-time JSON import.
3. Add focused tests and run the full validation suite.
4. Update the parent tracker facts and complete/move this packet.

## Acceptance criteria

- [ ] Runtime split monitor state is authoritative in SQLite.
- [ ] Legacy JSON is renamed only after a successful import commit and is never rewritten.
- [ ] All existing callers retain compatible helper signatures and dictionary shapes.
- [ ] Split phase, account, completion, and expiry behavior remains covered by focused tests.
- [ ] Focused tests, full unittest discovery, and compileall pass.

## Completion report

Report schema migration, preserved API behavior, legacy JSON handling, and exact validation results.
