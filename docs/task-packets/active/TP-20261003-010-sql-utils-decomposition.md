# TP-20261003-010: Decompose sql_utils.py by Domain

**Packet ID:** TP-20261003-010  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-010-sql-utils-decomposition.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-009  
**Priority:** Normal  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-009 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-009's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-009 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Decompose the large `utils/sql_utils.py` monolith only after persistence authority is stable, using a strangler migration that preserves public behavior.

## Target modules

Under `rsassistant/persistence/`:

```text
accounts.py
watchlists.py
orders.py
holdings.py
reverse_splits.py
```

Reuse modules already created by Packets 004–008. Do not duplicate repositories.

## Decomposition map

Move functions by ownership, preserving implementation first.

### accounts.py

Examples:

- account identity lookup/create;
- account nickname/mapping CRUD;
- account label queries;
- legacy mapping sync only if still needed.

### watchlists.py

- general watchlist CRUD;
- sell-list CRUD;
- legacy JSON migration only if still active.

Do not merge split-monitor tables unless their domain APIs genuinely align.

### orders.py

- OrderHistory CRUD/query;
- scheduled order/send-log repository if already housed here.

### holdings.py

- current holdings repository;
- historical holdings operations.

### reverse_splits.py

- ReverseSplitLog;
- ReverseSplitAccountEntries.

## Compatibility shim

Keep `utils/sql_utils.py` temporarily.

Preferred pattern:

```python
from rsassistant.persistence.accounts import ...
from rsassistant.persistence.orders import ...
...
```

Avoid wrapper functions unless a stable old signature needs adaptation.

Then migrate production callers from `utils.sql_utils` to domain modules in bounded groups.

At the end, search:

```bash
rg -n "utils\.sql_utils|from utils import sql_utils|from utils.sql_utils" .
```

Tests may continue to exercise compatibility imports until the next cleanup, but production imports should be zero where practical.

## Rules

- no query rewrites merely for style;
- no schema redesign;
- no changing returned dict/tuple shapes without tests + adapters;
- no Discord dependencies inside persistence modules;
- no circular imports back into `utils`.

## Tests

Move/partition `unittests/sql_utils_test.py` where useful, but do not require wholesale test-file restructuring.

Add import-contract tests for compatibility shim and direct repositories.

## Non-goals

- no `on_message.py` changes;
- no parser changes;
- no new database engine/ORM;
- no PostgreSQL migration.

## Acceptance criteria

- [ ] domain SQL implementations live under `rsassistant/persistence`.
- [ ] persistence modules do not import Discord contexts.
- [ ] production callers use domain repositories.
- [ ] `utils/sql_utils.py` is compatibility-only or very small.
- [ ] no behavior/schema redesign is mixed in.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report final function ownership map, remaining compatibility exports, production imports still pointing at `utils.sql_utils`, and tests.