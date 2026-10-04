# TP-20261003-008: OrderHistory Authority and CSV Demotion

**Packet ID:** TP-20261003-008  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-008-order-history-authority.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-007  
**Priority:** Normal  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-007 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-007's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-007 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Make SQLite `OrderHistory` the canonical order-history source and demote `orders_log.csv` to optional audit/export compatibility.

## Known current seams

- `utils/sql_utils.insert_order_history()` writes `OrderHistory`.
- `utils/csv_utils.save_order_to_csv()` still reads and rewrites `ORDERS_LOG_CSV`.
- `rsassistant/bot/cogs/split_monitor.py` has historically read order CSV.
- `rsassistant/bot/cogs/orders.py` and reporting paths may consume order helpers.

## First bounded inventory

Search current main for only:

```text
ORDERS_LOG_CSV
save_order_to_csv
load_csv_log
insert_order_history
OrderHistory
```

Record each production read/write in the completion report.

## Repository API

Create/extend `rsassistant/persistence/orders.py` with functions like:

```python
record_order(order)
list_orders(
    ticker=None,
    broker=None,
    action=None,
    start_date=None,
    end_date=None,
    limit=None,
)
latest_order(...)
```

Preserve current normalized field semantics.

If Packet 004 already created order persistence modules, place OrderHistory repository functions there rather than create a competing module.

## Writer flow

Target:

```text
parsed/executed order
 -> validate/normalize once
 -> record OrderHistory transaction
 -> optional CSV export
```

Do not write CSV first and then derive SQL input from reread CSV.

`CSV_LOGGING_ENABLED=false` must not suppress SQL order history.

## CSV export

If CSV remains useful:

- export from committed SQL;
- append/rebuild deterministically;
- label it audit/export in docs;
- no operational reader should require it.

## Tests

Cover:

- record and query OrderHistory;
- CSV disabled still records/queryable;
- existing CSV missing/stale does not affect order logic;
- split-monitor/order-history consumers use SQL;
- filter semantics;
- duplicate/order-id behavior;
- existing command output remains stable.

## Non-goals

- scheduled order queue was Packet 004;
- no order execution strategy changes;
- no Discord UX redesign;
- no Excel changes.

## Acceptance criteria

- [ ] OrderHistory is the sole operational order-history authority.
- [ ] no production decision reads `orders_log.csv`.
- [ ] CSV is optional export/audit only.
- [ ] `CSV_LOGGING_ENABLED=false` does not disable order history.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

List every remaining `ORDERS_LOG_CSV` reference and classify it as export/test/config or explain why it remains.