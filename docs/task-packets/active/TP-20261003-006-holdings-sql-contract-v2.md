# TP-20261003-006: Holdings SQL Contract v2

**Packet ID:** TP-20261003-006  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-006-holdings-sql-contract-v2.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-005  
**Priority:** High  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-005 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-005's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-005 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Create a SQL holdings contract that is actually capable of replacing CSV as the operational holdings authority. Do **not** switch production readers yet.

## Confirmed pre-dependency state

Current `HoldingsLive` is not sufficient:

- append-oriented;
- `quantity >= 0` constraint;
- `update_holdings_live_batch()` skips negative quantities;
- CSV preserves negative positions;
- current CSV row model includes broker/group/account identity, quantity, price, position value, account total, timestamp;
- readers infer “current” state from the latest CSV snapshot.

## Schema decision

Use a canonical current snapshot table plus transactional staging.

Recommended tables:

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

CREATE INDEX idx_holdings_current_ticker
ON holdings_current(ticker);

CREATE TABLE holdings_refresh_staging (
    refresh_id TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    position_value REAL NOT NULL,
    account_total REAL,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (refresh_id, account_id, ticker),
    FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
);
```

Negative `quantity` is valid.

## Atomic refresh contract

Implement repository operations approximately:

```python
begin_refresh(refresh_id)
stage_position(refresh_id, position)
commit_refresh(refresh_id, account_scope=None)
abort_refresh(refresh_id)
list_current_holdings(...)
latest_observed_at(...)
```

Recommended commit transaction:

```sql
BEGIN IMMEDIATE;
-- validate staged rows exist
-- delete affected current rows for refresh scope
-- insert staged rows into holdings_current
-- delete staging rows
COMMIT;
```

If the incoming snapshot represents all accounts, replace all `holdings_current`. If it is scoped, only replace that scope. Determine this from the existing refresh flow and document the decision in code/tests.

## Exact files

- shared migration module
- new `rsassistant/persistence/holdings.py`
- `utils/sql_utils.py` only for compatibility wrappers
- `utils/csv_utils.py` ingestion seam
- `utils/holdings_importer.py` only as required to supply normalized snapshot data
- holdings tests

## Ingestion changes

Separate normalization from persistence.

Create/retain a normalized position dict with:

```python
{
  "broker": ...,
  "broker_number": ...,
  "account_number": ...,
  "ticker": ...,
  "quantity": float,
  "price": float,
  "position_value": float,
  "account_total": float | None,
  "observed_at": "...",
  "source": "...",
}
```

Account identity should resolve through `Accounts`.

Do not make CSV existence a prerequisite for SQL persistence.

## Existing HoldingsLive

Do not delete it in this packet. Keep `HistoricalHoldings` behavior intact. Mark `HoldingsLive` legacy and stop adding new dependencies to it.

If existing historical aggregation still requires it, document the temporary bridge.

## Tests

Cover:

- negative quantity accepted;
- zero quantity;
- duplicate account+ticker upsert/replacement semantics;
- account resolution;
- full refresh atomicity;
- scoped refresh;
- abort leaves current snapshot unchanged;
- failed commit rolls back;
- latest observed timestamp;
- repeated refresh does not accumulate duplicates.

## Non-goals

- do not migrate holdings readers;
- do not remove CSV;
- do not redesign HistoricalHoldings;
- do not alter Discord commands.

## Acceptance criteria

- [ ] SQL can represent every normalized CSV holding row, including shorts/negative positions.
- [ ] current snapshot is atomic.
- [ ] CSV is not required to commit SQL.
- [ ] production readers are unchanged for now.
- [ ] HoldingsLive is not expanded as the new authority.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report final table schema, refresh scope semantics, repository API, treatment of HoldingsLive/HistoricalHoldings, tests, and any dependency-refresh changes.