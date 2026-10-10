# TP-20261003-004: Move Order Runtime State to SQLite

**Packet ID:** TP-20261003-004  
**Status:** Complete
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261003-004-order-runtime-sqlite.md`
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-003

## Objective

Store scheduled orders and sent-order audit entries in normalized SQLite tables, migrate existing SQLite queue payloads and legacy JSON files safely, and preserve the public helper APIs and returned dictionaries.

## Confirmed current state

- `utils/order_queue_manager.py` already uses SQLite table `order_queue(order_id, order_data)` after the previous migration, and can import `order_queue.json`.
- `utils/order_send_log_manager.py` still rewrites `order_send_log.json` and limits it to 1,000 records.
- The current queue API returns the original data dictionary, including any optional fields such as `status`.
- Queue and send-log managers have separate focused unittest modules.
- Schema migrations now live in `rsassistant/persistence/schema.py`, and `connect_runtime_db()` / `initialize_runtime_db()` are canonical from TP-20261003-003.

## Required changes

### `rsassistant/persistence/schema.py`

Add schema migration version 5.

Create `scheduled_orders` with the packet controller fields: `order_id`, `action`, `ticker`, `quantity`, `broker`, `scheduled_at`, `state`, `attempt_count`, `last_error`, `created_at`, and `updated_at`. Add `metadata_json TEXT NOT NULL DEFAULT '{}'` to preserve optional fields in the existing public queue dictionaries. Add an index on `scheduled_at`.

Create `rsa_order_send_log` with `send_id`, `sent_at`, `command`, `channel_id`, `ticker`, `action`, `quantity`, and `broker`; add indexes for send time and ticker/time.

If the existing `order_queue` table exists, parse its `order_data` records, import valid rows into `scheduled_orders`, then drop `order_queue` in the same migration. Preserve optional keys in `metadata_json`. Invalid individual SQL payloads should be skipped with a clear warning; the migration remains restart-safe.

### `utils/order_queue_manager.py`

Use `connect_runtime_db()` and the versioned schema. Keep all existing public functions and return shapes. Map dictionary key `time` to SQL `scheduled_at`, derive SQL `state` from optional `status` (default `pending`), and store all other optional dictionary keys in `metadata_json`. Reconstruct the exact public shape on reads.

Migrate `QUEUE_FILE` transactionally and idempotently. A malformed JSON document must raise and remain untouched. Skip/log malformed individual entries. Rename the JSON source to `.json.migrated` only after the import transaction commits. Repeated import after a failed rename must not duplicate rows.

### `utils/order_send_log_manager.py`

Replace whole-file read/modify/write with SQLite CRUD while preserving:

- `record_sent_rsa_order(...)`
- `list_sent_rsa_orders(limit=10, ticker=None, action=None)`
- `latest_sent_rsa_order(ticker=None)`

Return the same dictionary keys and filtering/order behavior. Use UTC ISO timestamps; normalize ticker/action as today. Keep the current maximum of 1,000 retained records by deleting oldest rows in the same transaction after inserts.

Migrate `ORDER_SEND_LOG_FILE` transactionally and idempotently. Malformed JSON leaves the full file untouched; malformed individual entries are skipped/logged. Rename to `.json.migrated` only after commit.

### Focused tests

Update `unittests/order_queue_manager_test.py` and `unittests/order_send_log_manager_test.py` to use temporary SQLite databases and legacy JSON paths. Cover queue shape preservation, typed scheduled-time updates, migration from the old SQL `order_queue` table, migration of both JSON files, repeated initialization, and source retention on malformed JSON.

## Non-goals

- Do not change order execution or Discord scheduling behavior.
- Do not migrate order-history CSV readers.
- Do not remove historical compatibility JSON files that have already been renamed `.migrated`.
- Do not change the public order-manager APIs.

## Implementation order

1. Add version-5 SQL tables and migrate existing `order_queue` rows.
2. Move the queue manager to `scheduled_orders` and migrate its legacy JSON input.
3. Move the sent-order manager to `rsa_order_send_log` and migrate its JSON input.
4. Run focused order tests, full unittest discovery, and compileall.
5. Update the parent tracker facts and complete/move this packet.

## Acceptance criteria

- [ ] Both operational order domains are SQLite-authoritative.
- [ ] Existing queue rows survive migration from the old SQL blob table.
- [ ] Both JSON sources archive only after successful committed imports.
- [ ] Repeated imports are idempotent and malformed documents remain available for recovery.
- [ ] Public API behavior and dictionary shapes remain compatible.
- [ ] Focused order tests, full unittest discovery, and compileall pass.

## Completion report

Report schema changes, migrations performed, legacy file behavior, API compatibility, and exact validation results.
