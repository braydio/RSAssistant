# Task Packet Tracker

Live execution ledger for canonical RSAssistant task packets.

Controlled statuses and lifecycle rules are defined in [README.md](README.md).

## Active packets

| Packet ID | Title | Status | Priority | Depends on | Target | Last updated | Packet |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TP-20261003-001 | RSAssistant Persistence Modernization and Decomposition | In Progress | High | None | main | 2026-10-03 | [packet](active/TP-20261003-001-rsassistant-persistence-modernization.md) |
| TP-20261004-002 | Performance Visibility and Growth History | Ready | High | TP-20261003-007, TP-20261004-001 | main | 2026-10-10 | [packet](active/TP-20261004-002-performance-visibility.md) |
| TP-20261003-012 | Parsing and Runtime Cleanup | Draft | Normal | TP-20261003-011 | main | 2026-10-03 | [packet](active/TP-20261003-012-parsing-runtime-cleanup.md) |

## Completed packets

| Packet ID | Title | Status | Completed | Packet |
| --- | --- | --- | --- | --- |
| TP-20261004-001 | Performance History Capture | Complete | 2026-10-10 | [packet](completed/TP-20261004-001-performance-history-capture.md) |
| TP-20261003-009 | Excel Runtime Retirement | Complete | 2026-10-04 | [packet](completed/TP-20261003-009-excel-retirement.md) |
| TP-20261003-010 | Decompose sql_utils.py by Domain | Complete | 2026-10-08 | [packet](completed/TP-20261003-010-sql-utils-decomposition.md) |
| TP-20261003-011 | Decompose on_message.py into Services | Complete | 2026-10-08 | [packet](completed/TP-20261003-011-on-message-decomposition.md) |
| TP-20261003-002 | Establish a Full CI Baseline | Complete | 2026-10-03 | [packet](completed/TP-20261003-002-ci-baseline.md) |
| TP-20261003-003 | Establish the SQLite Runtime Foundation | Complete | 2026-10-03 | [packet](completed/TP-20261003-003-sqlite-runtime-foundation.md) |
| TP-20261003-004 | Move Order Runtime State to SQLite | Complete | 2026-10-03 | [packet](completed/TP-20261003-004-order-runtime-sqlite.md) |
| TP-20261003-005 | Move Split Monitor State to SQLite | Complete | 2026-10-03 | [packet](completed/TP-20261003-005-split-monitor-sqlite.md) |
| TP-20261003-006 | Establish the Current Holdings SQL Contract | Complete | 2026-10-03 | [packet](completed/TP-20261003-006-holdings-sql-contract.md) |
| TP-20261003-007 | Make SQLite the Operational Holdings Read Source | Complete | 2026-10-03 | [packet](completed/TP-20261003-007-holdings-authority-inversion.md) |
| TP-20261004-008 | Make OrderHistory Authoritative and Demote Order CSV | Complete | 2026-10-04 | [packet](completed/TP-20261004-008-orderhistory-authority.md) |

## Historical / re-baseline queue

| Packet ID | Title | Status | Reason | Next action | Packet |
| --- | --- | --- | --- | --- | --- |
| TP-20260612-001 | Legacy RSAssistant Hardening Train (00–09) | Superseded | Packet assumptions no longer match current main; persistence packets 06/07 are visibly unimplemented and the train predates later repo changes. | Re-decompose against current main; reuse valid requirements selectively. | [wrapper](archived/TP-20260612-001-legacy-rsassistant-hardening-train.md) |

## Current modernization facts to preserve during re-baseline

- SQL/SQLite is already authoritative for several domains, including account mappings, watchlists/sell lists, order history, and reverse-split persistence.
- Excel runtime code, dependency, configuration, Docker mount, and startup directory creation were removed by TP-20261003-009; only historical migration documentation and user-owned workbooks remain.
- `utils/order_queue_manager.py` uses `scheduled_orders` in SQLite and imports `volumes/db/order_queue.json` once.
- `utils/order_send_log_manager.py` uses `rsa_order_send_log` in SQLite and imports `volumes/db/order_send_log.json` once.
- `utils/split_watch_utils.py` uses SQLite and imports `volumes/db/split_watchlist.json` once.
- `csv_utils.save_holdings_to_csv()` writes snapshots to `holdings_current`; active refreshes stage SQL until finalization. Holdings operational reads use SQL. The holdings CSV is optional compatibility output. `HoldingsLive` remains a positive-only append feed for historical snapshots.
- `OrderHistory` is the order-history authority. A present `orders_log.csv` is imported once through the `legacy_imports` ledger; optional exports are generated from SQL.
- `rsassistant/persistence/db.py` now owns runtime SQLite connections and initialization.
- The old hardening packets 06/07 describe useful target schemas but were not implemented.
- `rsassistant/persistence/performance.py` (migration 9, `account_value_snapshots`)
  durably records one effective-value snapshot per account on every committed
  holdings refresh, hooked into `holdings.replace_current_holdings()` and
  `holdings.activate_staged_holdings()`. `backfill_historical_account_values()`
  exists and is tested but has not yet been run against the real production
  database.

## Dependency-review protocol

Dependent modernization packets, including TP-20261004-002, were intentionally authored ahead of their prerequisites. Each contains the required review checkpoint:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

TP-20261004-001, TP-20261004-008, and TP-20261003-009 through TP-20261003-011 are complete locally. TP-20261003-011 passed unittest and compileall; pytest retains six unrelated failures listed in its completion report. TP-20261004-001 passed its own 12 focused tests plus full compileall/pytest with the same six pre-existing unrelated failures.

## Blockers

- TP-20261004-002 has completed its dependency refresh and is Ready.
- TP-20261003-012 remains Draft until TP-20261004-002 is implemented/reviewed and TP-012 is refreshed against the resulting code. Authoring/refresh chat: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e