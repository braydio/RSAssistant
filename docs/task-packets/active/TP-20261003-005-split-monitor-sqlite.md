# TP-20261003-005: Split Monitor Persistence to SQLite

**Packet ID:** TP-20261003-005  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-005-split-monitor-sqlite.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-004  
**Priority:** High  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-004 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-004's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-004 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Replace `utils/split_watch_utils.py` module-global/JSON state with transactional SQLite while preserving every caller-facing helper shape.

## Confirmed pre-dependency state

`utils/split_watch_utils.py` currently owns:

- global `data = {"watchlist": {}}`;
- `volumes/db/split_watchlist.json`;
- import-time `load_data()`;
- whole-file `save_data()`.

`rsassistant/bot/cogs/split_monitor.py` consumes this helper API.

## Required schema

Append the next migration after refresh:

```sql
CREATE TABLE split_monitor (
    ticker TEXT PRIMARY KEY,
    split_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('buying', 'selling')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE split_monitor_accounts (
    ticker TEXT NOT NULL,
    account_name TEXT NOT NULL,
    bought INTEGER NOT NULL DEFAULT 0 CHECK(bought IN (0,1)),
    sold INTEGER NOT NULL DEFAULT 0 CHECK(sold IN (0,1)),
    PRIMARY KEY (ticker, account_name),
    FOREIGN KEY (ticker) REFERENCES split_monitor(ticker) ON DELETE CASCADE
);
```

Do not reuse the existing general `watchlist` table. It represents a different workflow.

## Exact files

- shared migrations module
- new `rsassistant/persistence/split_monitor.py` repository
- `utils/split_watch_utils.py`
- `rsassistant/bot/cogs/split_monitor.py` only if compatibility adaptation is needed
- split-monitor tests; add `unittests/split_watch_utils_test.py` if none exists

## Repository API

Recommended repository functions:

```python
upsert_split(ticker, split_date, status="buying")
mark_bought(ticker, account_name)
mark_sold(ticker, account_name)
set_status(ticker, status)
fetch_split(ticker)
fetch_all_splits()
delete_split(ticker)
```

Keep `utils/split_watch_utils.py` as the compatibility/domain adapter until later decomposition.

Preserve public helpers:

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

Preserve returned status shape:

```python
{
    "split_date": "...",
    "status": "buying",
    "accounts_bought": [...],
    "accounts_sold": [...],
}
```

## Legacy migration

Input:

`volumes/db/split_watchlist.json`

Import once, transactionally, rename to `.migrated` only after committed success. No import-time mutable cache should remain.

## Tests

Cover all public helpers, date transition, cleanup, bought/sold equality cleanup, restart persistence, cascade delete, idempotent migration, malformed file preservation.

## Non-goals

- no general watchlist/sell-list redesign;
- no split strategy/business rule changes;
- no Discord UX changes.

## Acceptance criteria

- [ ] no module-global authoritative `data`.
- [ ] no runtime JSON writes for split monitor.
- [ ] helper API and dict shape remain compatible.
- [ ] migration is idempotent and transactional.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report schema version, repository functions, JSON migration result, test results, and any dependency-refresh changes.