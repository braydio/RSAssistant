# Packet 07: Split Monitor Persistence to SQLite

Commit: `refactor: migrate split monitor persistence to sqlite`

## Files

- `utils/runtime_db.py`
- `utils/split_watch_utils.py`
- `rsassistant/bot/cogs/split_monitor.py`
- split-monitor tests

## Schema

Do not reuse the existing SQL `watchlist` table; that belongs to the separate `WatchListManager` workflow.

Add:

```sql
CREATE TABLE IF NOT EXISTS split_monitor (
    ticker TEXT PRIMARY KEY,
    split_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('buying', 'selling')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS split_monitor_accounts (
    ticker TEXT NOT NULL,
    account_name TEXT NOT NULL,
    bought INTEGER NOT NULL DEFAULT 0,
    sold INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ticker, account_name),
    FOREIGN KEY (ticker) REFERENCES split_monitor(ticker) ON DELETE CASCADE
);
```

## Preserve API

Keep:
- `add_split_watch`
- `mark_account_bought`
- `update_split_status`
- `mark_account_sold`
- `cleanup_completed_tickers`
- `get_watchlist`
- `get_status`
- `get_full_watchlist`
- `remove_split_watch`
- `get_all_accounts`

Remove module-level mutable `data` and JSON `load_data()/save_data()` as the active store.

Return dictionaries in the same shape existing cog/callers expect.

## Legacy migration

Migrate `volumes/db/split_watchlist.json` transactionally and idempotently. Rename to `.migrated` only after successful commit; rollback/retain source on failure.

## Tests

- API shape preserved
- buying/selling state persists
- bought/sold account state persists
- completed cleanup works
- migration is idempotent
- failed migration preserves JSON
