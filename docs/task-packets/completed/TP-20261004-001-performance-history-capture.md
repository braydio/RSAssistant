# TP-20261004-001: Performance History Capture

**Packet ID:** TP-20261004-001  
**Status:** Complete  
**Created:** 2026-10-04  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261004-001-performance-history-capture.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-006  
**Priority:** High  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored before TP-20261003-006 lands.

After TP-20261003-006 is implemented, do not start this packet blindly. Re-open current main, inspect the final holdings schema/repository and its completion report, then refresh this packet if any table names, refresh semantics, normalized fields, or APIs changed.

If refresh is needed, stop before implementation and call it out here:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff:

> TP-20261003-006 has landed. Performance History Capture was pre-authored against the proposed holdings-v2 contract and needs review against the implemented schema before work begins: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

## Objective

Persist a durable account/portfolio value time series on every successful holdings refresh so RSAssistant can show recent value growth and historical trends.

This packet captures data only. The Discord summaries/charts are TP-20261004-002.

## Important metric semantics

Do not call simple account-value change "investment return."

RSAssistant does not currently have a reliable external deposit/withdrawal cash-flow ledger. Therefore:

- `value_change` = change in observed account/portfolio value;
- `value_change_pct` = percentage change in observed value;
- `positions_value` = sum of security position values;
- `reported_account_total` = account total reported by the holdings source, when available;
- true time-weighted or money-weighted investment return is **out of scope** until external cash flows are modeled.

Document this distinction in code and user-facing docs.

## Confirmed pre-dependency state

Current repository evidence:

- holdings parser/import path already carries `account_total`;
- CSV rows carry `Position Value`, `Account Total`, and `Timestamp`;
- legacy `HistoricalHoldings` stores per-account/ticker/day:
  - quantity
  - average_price
- current `..history` plots **quantity**, not portfolio/account value;
- `HistoricalHoldings` does not preserve reported account totals or cash;
- TP-20261003-006 is intended to introduce authoritative `holdings_current` with:
  - account_id
  - ticker
  - quantity
  - price
  - position_value
  - account_total
  - observed_at
  - source

## Required schema

Append the next migration after refreshing against TP-20261003-006.

Create a snapshot table:

```sql
CREATE TABLE account_value_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    refresh_id TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    positions_value REAL NOT NULL,
    reported_account_total REAL,
    effective_value REAL NOT NULL,
    valuation_basis TEXT NOT NULL
        CHECK(valuation_basis IN ('reported_total', 'positions_sum', 'historical_positions_sum')),
    source TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES Accounts(account_id),
    UNIQUE (refresh_id, account_id)
);

CREATE INDEX idx_account_value_snapshots_account_time
ON account_value_snapshots(account_id, observed_at);

CREATE INDEX idx_account_value_snapshots_time
ON account_value_snapshots(observed_at);
```

### Value rules

For each account in a successfully committed holdings refresh:

```text
positions_value =
    SUM(position_value) for all current positions in that account

reported_account_total =
    one normalized account_total for that account when source provides a positive/valid total,
    otherwise NULL

effective_value =
    reported_account_total when present
    otherwise positions_value

valuation_basis =
    "reported_total" when reported_account_total is used
    otherwise "positions_sum"
```

Do not sum repeated `account_total` values from each ticker row. Normalize one account total per account per refresh.

If multiple non-null reported totals disagree within one refresh, treat that as snapshot validation failure for that account or choose the last/authoritative source only if TP-20261003-006 defines a deterministic rule. Do not average conflicting account totals silently.

## Atomicity

A performance snapshot must represent the **same committed refresh** as `holdings_current`.

Preferred implementation:

- TP-20261003-006 exposes a refresh ID;
- during the same final commit or immediately after it in the same transaction, insert one `account_value_snapshots` row per affected account;
- if holdings refresh rolls back, performance snapshot rows must roll back too.

Do not create a value snapshot from partially staged holdings.

## Repository API

Add to `rsassistant/persistence/holdings.py` or a dedicated `performance.py` only if separation is already warranted.

Recommended functions:

```python
record_account_value_snapshots(conn, refresh_id, accounts, observed_at, source)
list_account_value_snapshots(
    account_ids=None,
    start_at=None,
    end_at=None,
)
latest_account_values(account_ids=None)
portfolio_value_series(start_at=None, end_at=None)
account_value_series(account_id, start_at=None, end_at=None)
```

Prefer repository functions to raw SQL in Discord code.

## Historical backfill

Existing `HistoricalHoldings` can provide **positions-value history**, but not historical reported account totals.

Add an idempotent one-time backfill:

```sql
SELECT
    account_id,
    date,
    SUM(quantity * average_price) AS positions_value
FROM HistoricalHoldings
GROUP BY account_id, date
```

Write rows using:

```text
reported_account_total = NULL
effective_value = positions_value
valuation_basis = "historical_positions_sum"
source = "historical_holdings_backfill"
```

Use deterministic refresh IDs, e.g.:

```text
historical:<YYYY-MM-DD>:<account_id>
```

so the backfill is repeatable.

### Do not blur the basis boundary

Historical rows derived from position sums may exclude cash/uninvested balance that newer reported totals include.

Preserve `valuation_basis` so the visibility layer can disclose this and avoid pretending the series is perfectly apples-to-apples.

## Retention

Do not prematurely downsample.

The expected holdings refresh cadence is modest enough for SQLite to retain account-level refresh snapshots. If storage growth later becomes material, introduce rollups in a separate packet with measured evidence.

## Exact files

Expected after dependency refresh:

- shared migration module under `rsassistant/persistence/`;
- `rsassistant/persistence/holdings.py` and/or `performance.py`;
- holdings refresh commit path from TP-20261003-006;
- `utils/sql_utils.py` only if a compatibility export is needed;
- performance/history tests;
- documentation for metric semantics.

## Tests

Cover:

- one snapshot per account per refresh;
- repeated ticker rows do not multiply account_total;
- reported total preferred when valid;
- positions sum fallback;
- negative positions included in positions_value;
- refresh rollback creates no performance rows;
- scoped refresh updates only affected account snapshots;
- same refresh ID is idempotent;
- HistoricalHoldings backfill;
- repeated backfill has no duplicates;
- valuation basis preserved;
- latest/series queries order correctly.

## Non-goals

- no Discord performance command;
- no chart changes;
- no cash-flow-adjusted investment return;
- no benchmark comparison;
- no market-data backfill beyond values already stored by RSAssistant.

## Acceptance criteria

- [x] every committed holdings refresh can persist account value snapshots.
- [x] recent and historical value queries have durable data.
- [x] account totals are not double-counted across positions.
- [x] historical positions-value data is backfilled where available (function
      added; not yet invoked against the real production database).
- [x] historical position-sum data is distinguishable from newer reported-total data.
- [x] failed holdings refreshes cannot create phantom growth points.

## Validation

Run focused performance/holdings tests, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

## Completion report

1. Migration 9 (`LATEST_SCHEMA_VERSION` 8 → 9) adds `account_value_snapshots`
   plus its two indexes, in `rsassistant/persistence/schema.py`.
2. `effective_value = reported_account_total` when exactly one distinct
   non-null `account_total` is present for that account in the commit,
   otherwise `positions_value` (`SUM(position_value)` over that account's
   current positions).
3. Conflicting (more than one distinct non-null) totals fall back to
   `positions_sum` with a logged warning naming the account; never averaged,
   never blocks the holdings commit.
4. `record_account_value_snapshots(conn, ...)` is called inside the same
   `BEGIN IMMEDIATE` transaction as both `holdings.replace_current_holdings()`
   and `holdings.activate_staged_holdings()`, so an aborted/discarded staged
   refresh (which never reaches those functions) produces no snapshot rows.
5. `backfill_historical_account_values()` was added and tested against
   synthetic `HistoricalHoldings` rows (idempotent via the `legacy_imports`
   ledger); it has not yet been invoked against the real production
   database — that's an explicit operator action, not done as part of this
   packet.
6. No real history exists yet; it starts accumulating from the next holdings
   refresh and from whenever the backfill is actually run against production
   data.
7. `unittests/performance_repository_test.py`: 12/12 passed, covering every
   item in this packet's test list. `python -m compileall -q rsassistant
   utils plugins unittests`: passed. `python -m pytest -q`: 171 passed, 6
   failed — the same pre-existing, unrelated `RSAssistant.watch_list_manager`
   monkeypatch failures called out in TP-20261003-009/010/011; unchanged by
   this packet. Two unrelated tests hardcoded `PRAGMA user_version == 8`
   (`unittests/sql_utils_test.py`, `unittests/order_queue_manager_test.py`)
   and were updated to 9.
8. TP-20261003-006 landed with the refresh lifecycle always doing a full
   `holdings_current` replace (not incremental per-account updates), so
   "affected accounts" is every account in the new snapshot. The pre-authored
   `record_account_value_snapshots(conn, refresh_id, accounts, observed_at,
   source)` signature was adapted to make `accounts`/`observed_at` optional,
   defaulting to aggregating `holdings_current` directly via `conn`; the
   historical backfill path still supplies `accounts` explicitly since its
   data comes from `HistoricalHoldings`. Full detail in
   `docs/task-packets/summaries/TP-20261004-001-SUMMARY.md`.
