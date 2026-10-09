# Task Packet Tracker

Live execution ledger for canonical RSAssistant task packets.

Controlled statuses and lifecycle rules are defined in [README.md](README.md).

## Active packets

| Packet ID | Title | Status | Priority | Depends on | Target | Last updated | Packet |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TP-20261003-001 | RSAssistant Persistence Modernization and Decomposition | Ready | High | None | main | 2026-10-03 | [packet](active/TP-20261003-001-rsassistant-persistence-modernization.md) |
| TP-20261003-002 | CI Baseline Completion | Ready | High | None | main | 2026-10-03 | [packet](active/TP-20261003-002-ci-baseline-completion.md) |
| TP-20261003-003 | SQLite Runtime Foundation Completion | Draft | High | TP-20261003-002 | main | 2026-10-03 | [packet](active/TP-20261003-003-sqlite-runtime-foundation.md) |
| TP-20261003-004 | Order Runtime Persistence Completion | Draft | High | TP-20261003-003 | main | 2026-10-03 | [packet](active/TP-20261003-004-order-runtime-sqlite.md) |
| TP-20261003-005 | Split Monitor Persistence to SQLite | Draft | High | TP-20261003-004 | main | 2026-10-03 | [packet](active/TP-20261003-005-split-monitor-sqlite.md) |
| TP-20261003-006 | Holdings SQL Contract v2 | Draft | High | TP-20261003-005 | main | 2026-10-03 | [packet](active/TP-20261003-006-holdings-sql-contract-v2.md) |
| TP-20261004-001 | Performance History Capture | Draft | High | TP-20261003-006 | main | 2026-10-04 | [packet](active/TP-20261004-001-performance-history-capture.md) |
| TP-20261003-007 | Holdings Authority Inversion | Draft | High | TP-20261004-001 | main | 2026-10-04 | [packet](active/TP-20261003-007-holdings-authority-inversion.md) |
| TP-20261004-002 | Performance Visibility and Growth History | Draft | High | TP-20261003-007, TP-20261004-001 | main | 2026-10-04 | [packet](active/TP-20261004-002-performance-visibility.md) |
| TP-20261003-008 | OrderHistory Authority and CSV Demotion | Draft | Normal | TP-20261004-002 | main | 2026-10-04 | [packet](active/TP-20261003-008-order-history-authority.md) |
| TP-20261003-009 | Excel Runtime Retirement | Draft | Normal | TP-20261003-008 | main | 2026-10-03 | [packet](active/TP-20261003-009-excel-retirement.md) |
| TP-20261003-010 | Decompose sql_utils.py by Domain | Draft | Normal | TP-20261003-009 | main | 2026-10-03 | [packet](active/TP-20261003-010-sql-utils-decomposition.md) |
| TP-20261003-011 | Decompose on_message.py into Services | Draft | Normal | TP-20261003-010 | main | 2026-10-08 | [packet](active/TP-20261003-011-on-message-decomposition.md) |
| TP-20261003-012 | Parsing and Runtime Cleanup | Draft | Normal | TP-20261003-011 | main | 2026-10-03 | [packet](active/TP-20261003-012-parsing-runtime-cleanup.md) |

## Historical / re-baseline queue

| Packet ID | Title | Status | Reason | Next action | Packet |
| --- | --- | --- | --- | --- | --- |
| TP-20260612-001 | Legacy RSAssistant Hardening Train (00–09) | Superseded | Packet assumptions no longer match current main; persistence packets 06/07 are visibly unimplemented and the train predates later repo changes. | Re-decompose against current main; reuse valid requirements selectively. | [wrapper](archived/TP-20260612-001-legacy-rsassistant-hardening-train.md) |

## Current modernization facts to preserve during re-baseline

- SQL/SQLite is already authoritative for several domains, including account mappings, watchlists/sell lists, order history, and reverse-split persistence.
- Excel writes are hard-disabled, but `utils/excel_utils.py`, `openpyxl`, Excel config, and Docker volume/runtime directories remain.
- `utils/order_queue_manager.py` still uses `volumes/db/order_queue.json`.
- `utils/order_send_log_manager.py` still uses `volumes/db/order_send_log.json`.
- `utils/split_watch_utils.py` still uses a module-level JSON-backed watchlist.
- Holdings ingestion writes SQL, but operational reads still heavily depend on `volumes/logs/holdings_log.csv`.
- `utils/runtime_db.py` does not exist on current main.
- The old hardening packets 06/07 describe useful target schemas but were not implemented.

## Dependency-review protocol

Dependent modernization packets, including TP-20261004-001 and TP-20261004-002, were intentionally authored ahead of their prerequisites. Each contains the required review checkpoint:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

After a dependency lands, review its implementation and refresh the next packet against current main before changing that packet from Draft to Ready.

## Blockers

- **TP-20261003-011:** structure-refresh completed 2026-10-08, but the remotely visible GitHub `main` did not contain the reported landed TP-20261003-010 implementation during refresh. Keep TP-011 Draft until the execution checkout/current main visibly contains TP-010 and its persistence import seams are reconciled. Authoring/refresh chat: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e
- Other dependent packets remain Draft until their dependency is reviewed.