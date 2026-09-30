# Packet 06: Order Runtime Persistence to SQLite

Commit: `refactor: migrate order runtime persistence to sqlite`

## Files

- `utils/runtime_db.py` (new)
- `utils/order_queue_manager.py`
- `utils/order_send_log_manager.py`
- `utils/order_exec.py` only if state/attempt updates require it
- `rsassistant/bot/tasks.py` only if queue query behavior requires it
- `unittests/order_queue_manager_test.py`
- `unittests/order_send_log_manager_test.py`
- directly affected order tests

## Runtime DB

Operational persistence must not depend on `SQL_LOGGING_ENABLED`. Do not route it through `sql_utils.get_db_connection()`, which currently raises when historical SQL logging is disabled.

Create `utils/runtime_db.py` using the existing `SQL_DATABASE` path:

```python
def connect_runtime_db():
    conn = sqlite3.connect(SQL_DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

Initialize:

```sql
CREATE TABLE IF NOT EXISTS scheduled_orders (
    order_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    broker TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rsa_order_send_log (
    send_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    command TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    broker TEXT NOT NULL
);
```

Add indexes for scheduled time and send-log timestamp/ticker where useful.

## Preserve public APIs

Keep call-site APIs stable:

```
add_to_order_queue
get_order_queue
remove_order
update_order_time
clear_order_queue
list_order_queue
list_order_queue_items
get_past_due_orders

record_sent_rsa_order
list_sent_rsa_orders
latest_sent_rsa_order
```

Implement them transactionally with SQLite.

Map existing queue `time` field to `scheduled_at` internally while preserving the returned dictionary shape expected by current callers.

## Legacy migration

Automatically migrate:
- `volumes/db/order_queue.json`
- `volumes/db/order_send_log.json`

Rules:
1. create tables
2. begin transaction
3. parse legacy file
4. import valid rows idempotently
5. commit
6. only after successful commit rename source to `*.migrated`
7. on failure rollback and leave original JSON untouched

Malformed individual rows may be logged/skipped. A JSON decode failure leaves the entire source untouched.

Migration must be safe to run repeatedly.

## Tests

- all existing public API behavior remains compatible
- writes survive a new connection/process
- concurrent logical updates do not rewrite whole files
- both legacy files migrate once
- repeated migration creates no duplicates
- failed migration leaves source JSON intact
