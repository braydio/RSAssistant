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

## Resource optimization train (2026-10-10)

The following packets were audited on `main@b35ea948`. TP-001 through TP-009 are independently executable Ready workstreams (recommended order 001, 005, 004, 002, 003, 006, 007, 008, 009). TP-010/011 are intentionally Draft pending their modernization dependency and a targeted refresh. No measured runtime reductions are claimed from static inspection.

| Packet ID | Title | Status | Priority | Depends on | Target | Last updated | Packet |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TP-20261010-001 | Runtime Resource Baseline and Regression Instrumentation | Ready | High | None | main | 2026-10-10 | [packet](active/TP-20261010-001-runtime-resource-baseline.md) |
| TP-20261010-002 | Replace Threaded Scheduler with Asyncio-Native Jobs | Ready | High | None | main | 2026-10-10 | [packet](active/TP-20261010-002-asyncio-native-scheduler.md) |
| TP-20261010-003 | Keep Network and Disk Operations off Discord Event Loop | Ready | High | None | main | 2026-10-10 | [packet](active/TP-20261010-003-nonblocking-discord-network.md) |
| TP-20261010-004 | Make Holdings Snapshot Import Change-Driven and Retry-Safe | Ready | High | None | main | 2026-10-10 | [packet](active/TP-20261010-004-holdings-import-change-detection.md) |
| TP-20261010-005 | Bound Logging Memory, Disk Churn, and Sensitive Payloads | Ready | High | None | main | 2026-10-10 | [packet](active/TP-20261010-005-bounded-and-safe-logging.md) |
| TP-20261010-006 | Bound Market Price Cache and Minimize Disk Writes | Ready | Normal | None | main | 2026-10-10 | [packet](active/TP-20261010-006-price-cache-bounds-and-atomicity.md) |
| TP-20261010-007 | ULT-MA Plugin Nonblocking Market Data and Idle Efficiency | Ready | Normal | None | main | 2026-10-10 | [packet](active/TP-20261010-007-ultma-idle-and-async-market-data.md) |
| TP-20261010-008 | Lean Docker Image, Startup I/O, and Health Checks | Ready | Normal | None | main | 2026-10-10 | [packet](active/TP-20261010-008-lean-container-startup.md) |
| TP-20261010-009 | Stop Shipping Runtime Artifacts and Add Safe Retention | Ready | Normal | None | main | 2026-10-10 | [packet](active/TP-20261010-009-artifact-hygiene-and-retention.md) |
| TP-20261010-010 | Replace Per-Ticker Holdings CSV Scans with One SQL Read | Draft | High | TP-20261003-007 and TP-20261003-011 (dependency refresh required) | main | 2026-10-10 | [packet](active/TP-20261010-010-holdings-summary-single-pass.md) |
| TP-20261010-011 | Consolidate Long-Sleep Order Tasks without Changing Execution Semantics | Draft | High | TP-20261003-004 (dependency refresh required) | main | 2026-10-10 | [packet](active/TP-20261010-011-scheduled-order-timer-consolidation.md) |

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