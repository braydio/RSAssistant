# TP-20261003-010: Decompose sql_utils.py by Domain

**Packet ID:** TP-20261003-010
**Status:** Complete
**Created:** 2026-10-03
**Last updated:** 2026-10-08
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/completed/TP-20261003-010-sql-utils-decomposition.md`
**Workstream size:** One implementation packet
**Depends on:** TP-20261003-009
**Priority:** Normal
**Controller:** TP-20261003-001

## Dependency-refresh checkpoint (2026-10-08)

This packet was authored **before TP-20261003-009 landed**. The completion report and current persistence tree were reviewed before implementation.

Before coding:

1. Re-open current repository state and the TP-009 completion report.
2. Compare the named persistence modules and public APIs against the current tree.
3. Preserve the review link for traceability:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-009 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Review finding: TP-009 completed Excel retirement and did not change SQL ownership or schemas. Existing `rsassistant/persistence/orders.py` and `holdings.py` are the packet's previously planned reused repositories. `accounts.py`, `watchlists.py`, and `reverse_splits.py` are still absent. SQL schemas and public APIs remain present in `utils/sql_utils.py`; no material assumption changed. Proceed with this packet.


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

- [x] domain SQL implementations live under `rsassistant/persistence`.
- [x] persistence modules do not import Discord contexts.
- [x] production callers use domain repositories.
- [x] `utils/sql_utils.py` is compatibility-only or very small.
- [x] no behavior/schema redesign is mixed in.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

- Account identity, nickname mapping, label, and resolution APIs live in `rsassistant/persistence/accounts.py`.
- Watchlist/sell-list CRUD and legacy JSON migration live in `rsassistant/persistence/watchlists.py`.
- OrderHistory CRUD and legacy event/CSV adaptation live in `rsassistant/persistence/orders.py`.
- Current and historical holdings operations live in `rsassistant/persistence/holdings.py`.
- Reverse split log and account-entry APIs live in `rsassistant/persistence/reverse_splits.py`.
- Validated generic table queries live in `rsassistant/persistence/admin.py`; coordinated schema and legacy import startup lives in `rsassistant/persistence/runtime.py`.
- `utils/sql_utils.py` is a 196-line compatibility facade. It retains legacy names and patchable configuration constants, including `init_db`, normalized-order validation, CSV-shaped order insertion, current-holdings snapshot helpers, and the operator query adapter.
- Production Python imports of `utils.sql_utils` are zero. Text search found only a historical API mention in an older completed packet; the current config documentation no longer points callers there.
- `python -m unittest discover -s unittests -p '*_test.py'`: 83 tests passed.
- `python -m compileall -q rsassistant utils plugins unittests`: passed.
- `python -m pytest -q`: 152 passed, 7 failed. The failures are outside this packet: two tests assume `RSAssistant` exports `discord`/`bot`, one round-up snippet expectation, two command tests invoke decorated Discord commands with a missing context, and two sell-queue tests assume a module-level `RSAssistant.watch_list_manager` export. They were left unchanged per the packet's instruction to document unrelated failures.
- No query/schema redesign was introduced. The watch utility test fixture now redirects the direct watchlist and holdings repository database paths alongside legacy shim paths.
