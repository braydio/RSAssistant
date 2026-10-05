# TP-20261003-006: Establish the Current Holdings SQL Contract

**Packet ID:** TP-20261003-006  
**Status:** Complete
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261003-006-holdings-sql-contract.md`
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-003

## Objective

Add a SQL current-position snapshot contract that represents the full holdings row identity and negative quantities, and make holdings ingestion write that contract atomically before any operational readers move to it.

## Confirmed current state

- `HoldingsLive` is append-oriented, requires non-negative quantity, and omits broker/account totals and source identity beyond `account_id`.
- `utils.sql_utils.update_holdings_live_batch()` skips negative positions.
- `utils.csv_utils.save_holdings_to_csv()` validates/normalizes complete rows, then appends only non-negative positions to `HoldingsLive`.
- Holdings refresh already has a CSV staging lifecycle: `begin_holdings_refresh()`, `save_holdings_to_csv()`, `finalize_holdings_refresh()`, and `abort_holdings_refresh()`.
- Historical holdings use `HoldingsLive`; keep that historical feed separate from the new current snapshot table until readers migrate in Packet 6.

## Required changes

### `rsassistant/persistence/schema.py`

Add migration version 7 with:

```sql
CREATE TABLE holdings_current (
    account_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    position_value REAL NOT NULL,
    account_total REAL,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (account_id, ticker),
    FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
);
```

Add refresh marker and staging tables keyed by `refresh_id` so partial broker batches remain invisible until `finalize_holdings_refresh()` activates them. Staging rows use the same fields and account/ticker identity as current rows.

### `rsassistant/persistence/holdings.py`

Create validated APIs to atomically replace the current snapshot, stage/replace one refresh snapshot, activate a staged refresh, discard an aborted refresh, and read current rows. Resolve account IDs through `Accounts` in the same write transaction. Allow finite negative quantities. Reject malformed identities, dates, or non-finite numeric values before deleting or replacing existing rows.

Use `BEGIN IMMEDIATE` for replacement/activation transactions. If any insert fails, the previous current snapshot must remain intact.

### `utils/sql_utils.py`

Add compatibility delegates for the new repository APIs. Keep `update_holdings_live_batch()` as the existing append-only historical observation path; do not use `HoldingsLive` as the current snapshot contract.

### `utils/csv_utils.py`

After full row normalization and validation, map all rows—including negative positions—into the SQL current snapshot API. When no full refresh is active, replace the current snapshot transactionally. During a refresh, update the SQL staging generation keyed by the `.next` CSV path; activate it only after `finalize_holdings_refresh()` validates the complete staged CSV. `abort_holdings_refresh()` must discard the corresponding SQL staging generation.

Keep positive-only `HoldingsLive` appends for historical observation compatibility. Do not move any holdings readers in this packet.

### Tests

Add `unittests/holdings_repository_test.py` for negative quantities, account identity, account totals/timestamps, staging visibility, atomic replacement rollback, activation, and discard. Update `unittests/csv_utils_test.py` for current-snapshot ingestion and refresh staging, while retaining tests for the legacy historical feed.

## Non-goals

- Do not migrate any holdings readers from CSV; Packet 6 owns authority inversion.
- Do not remove or redesign `HoldingsLive` or `HistoricalHoldings`.
- Do not change the CSV schema or public CSV helper signatures.

## Implementation order

1. Add migration version 7 and the holdings repository.
2. Add `sql_utils` compatibility delegates.
3. Wire normalized full snapshots and refresh lifecycle into `csv_utils`.
4. Add focused tests, then run full unittest discovery and compileall.
5. Update the parent tracker facts and complete/move this packet.

## Acceptance criteria

- [ ] SQL current holdings preserve broker/account identity, totals, timestamps, source, and negative quantity.
- [ ] Current snapshot replacement and refresh activation are atomic.
- [ ] Partial refresh batches do not replace active current holdings before finalization.
- [ ] CSV ingestion writes every normalized current row to SQL while preserving legacy historical observations.
- [ ] Existing readers remain unchanged for Packet 6.
- [ ] Focused tests, full unittest discovery, and compileall pass.

## Completion report

Report schema shape, transaction semantics, staging lifecycle, compatibility behavior, and validation results.
