# TP-20261003-004: Order Runtime Persistence Completion

**Packet ID:** TP-20261003-004  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-004-order-runtime-sqlite.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-003  
**Priority:** High  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-003 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-003's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-003 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Finish the partial order-runtime migration: normalize scheduled orders into typed SQLite columns, migrate the sent-order audit log to SQLite, and preserve all current helper APIs.

## Confirmed pre-dependency state

- `utils/order_queue_manager.py` has already moved off active JSON writes.
- It currently stores opaque JSON in SQLite table `order_queue(order_id, order_data,...)`.
- It still uses `order_queue.json` as one-time legacy input.
- `utils/order_send_log_manager.py` still uses `order_send_log.json` as the live store.
- DB migrations already exist under the shared DB foundation.

## Required schema migration

Append the next migration version after the dependency lands. Do not assume the numeric version in this pre-authored packet.

Create typed table:

```sql
CREATE TABLE scheduled_orders (
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
CREATE INDEX idx_scheduled_orders_scheduled_at
ON scheduled_orders(scheduled_at);
```

Create audit table:

```sql
CREATE TABLE rsa_order_send_log (
    send_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    command TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    broker TEXT NOT NULL
);
CREATE INDEX idx_rsa_order_send_log_sent_at
ON rsa_order_send_log(sent_at DESC);
CREATE INDEX idx_rsa_order_send_log_ticker_sent_at
ON rsa_order_send_log(ticker, sent_at DESC);
```

### Existing SQLite `order_queue` migration

If `order_queue` exists, parse each `order_data` JSON row and migrate valid entries to `scheduled_orders` idempotently.

Mapping:

```text
order_id -> order_id
data["action"] -> action
data["ticker"] -> ticker
data["quantity"] -> quantity
data["broker"] -> broker
data["time"] -> scheduled_at
```

Do not drop `order_queue` until migration tests prove conversion is safe. It may remain as a deprecated compatibility table for one release.

### Legacy JSON files

- `volumes/db/order_queue.json`
- `volumes/db/order_send_log.json`

Import transactionally and idempotently. Rename to `*.migrated` only after committed import. Malformed whole-file JSON must leave source untouched.

## Exact files

- shared migration module from Packet 003
- `utils/order_queue_manager.py`
- `utils/order_send_log_manager.py`
- `unittests/order_queue_manager_test.py`
- `unittests/order_send_log_manager_test.py`
- `unittests/order_queue_tasks_test.py`
- directly affected order tests

## Public API compatibility

Preserve:

```text
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

Returned order dicts must still expose `time`, not `scheduled_at`, to existing callers.

Recommended adapter:

```python
def _row_to_order(row):
    return {
        "action": row["action"],
        "ticker": row["ticker"],
        "quantity": row["quantity"],
        "broker": row["broker"],
        "time": row["scheduled_at"],
    }
```

## Tests

Cover:

- typed round trip;
- update time;
- removal/clear;
- past-due query;
- restart/new connection persistence;
- old SQLite blob-table migration;
- both JSON migrations;
- repeated migration no duplicates;
- malformed source preservation;
- send-log filters/limits/order;
- concurrency-sensitive writes do not rewrite a whole file.

## Non-goals

- no OrderHistory redesign;
- no Discord order command rewrite;
- no retention-policy redesign beyond preserving current 1000-entry behavior if still desired.

## Implementation order

1. dependency refresh;
2. add schema migration;
3. migrate scheduled-order helper;
4. migrate send-log helper;
5. compatibility migration;
6. tests.

## Acceptance criteria

- [ ] no active order queue mutation uses JSON files.
- [ ] no active sent-order audit mutation uses JSON files.
- [ ] typed scheduled-order columns exist.
- [ ] existing helper API shapes remain stable.
- [ ] legacy files are import-only.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report schema version added, migrated legacy sources, compatibility table/shim retained, tests, and any packet refresh changes.