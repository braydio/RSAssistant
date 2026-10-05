# TP-20261004-008: Make OrderHistory Authoritative and Demote Order CSV

**Packet ID:** TP-20261004-008
**Status:** Complete
**Created:** 2026-10-04
**Last updated:** 2026-10-04
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/completed/TP-20261004-008-orderhistory-authority.md`
**Workstream size:** One implementation packet
**Depends on:** TP-20261003-003, TP-20261003-004, TP-20261003-007

## Goal

Use `OrderHistory` as the authoritative order-history source. Existing `orders_log.csv` data is a one-time legacy import input; thereafter the file is optional generated compatibility output. Order-history commands and queries must work with CSV logging disabled and the CSV absent.

## Confirmed current seams

- `utils/parsing_utils.py` calls `utils.sql_utils.insert_order_history()` for parsed order events.
- `utils/sql_utils.py` owns the `OrderHistory` table writes but exposes no domain read query.
- `rsassistant/bot/cogs/split_monitor.py::SplitMonitorCog.split_orders()` reads `ORDERS_LOG_CSV` and refuses to run when CSV logging is disabled.
- `utils/csv_utils.py::save_order_to_csv()` currently treats CSV as the write store and reads it back for de-duplication. No production call site currently invokes this helper.
- `utils/utility_utils.py::get_order_details()` is a commented-out CSV implementation and has no callers. Replace it with a functional SQL-backed compatibility query or remove it only if no public compatibility concern exists.

## Implementation

1. Add `rsassistant/persistence/orders.py` with `list_order_history(ticker=None, broker=None, limit=None)` returning dictionaries containing `order_id`, `broker`, `broker_name`, `broker_number`, `account_number`, `ticker`, `date`, `action`, `quantity`, `price`, `total_value`, and `timestamp`. Use parameterized filters and deterministic newest-first ordering (`date`, then `timestamp`, then `order_id`).
2. Add a schema migration for an idempotency ledger for one-time legacy CSV import (source path/key, completion time, imported row count). Import a present `ORDERS_LOG_CSV` once, transactionally, using stable deterministic IDs derived from normalized source row plus row ordinal; malformed rows must not cause partial import or be silently dropped. Leave malformed source untouched and report the reason.
3. Make `split_orders()` query `list_order_history(ticker=...)`, apply the optional broker filter to SQL/domain rows, and preserve current output text and empty-state behavior. Remove CSV existence/config gates.
4. Replace `save_order_to_csv()` with a compatibility facade that writes/updates SQL first, then optionally exports authoritative SQL history when CSV logging is enabled. SQL remains committed if export fails. Do not use the CSV as a de-duplication/read source.
5. Implement the dormant `get_order_details()` as a SQL query preserving broker/account/ticker matching and its current return string shape. Resolve the existing account-number suffix behavior consistently; fix the Fidelity branch, which currently never assigns `account_in_csv`.
6. Add focused repository, legacy import, disabled-CSV command, and compatibility-export tests.

## Non-goals

- Do not change scheduled-order queue or sent-order audit storage; those are already SQLite-backed.
- Do not change broker execution or scheduling semantics.
- Do not delete `orders_log.csv`; retain it as an operator-readable export.
- Do not migrate holdings or split-watch persistence in this packet.

## Validation

```bash
python -m pytest -q unittests/order_history_repository_test.py unittests/split_monitor_test.py unittests/csv_utils_test.py unittests/utility_utils_test.py
python -m unittest discover -s unittests -p '*_test.py'
python -m compileall .
```

## Acceptance criteria

- Legacy order rows import exactly once and atomically; malformed CSV is retained and no partial SQL import occurs.
- `splitorders` and `get_order_details()` read only SQL and work with CSV disabled or absent.
- CSV export is generated from SQL state and cannot become the source of operational reads.
- Focused and full validation pass.
