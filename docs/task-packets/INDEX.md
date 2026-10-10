# Task Packet Index

Canonical packet discovery index for `braydio/RSAssistant`.

See [README.md](README.md) for naming, lifecycle, persistence, and authoring rules. See [TRACKER.md](TRACKER.md) for live execution state.

## Active

| Packet ID | Title | Status | Priority | Canonical packet |
| --- | --- | --- | --- | --- |
| TP-20261003-001 | RSAssistant Persistence Modernization and Decomposition | In Progress | High | [active/TP-20261003-001-rsassistant-persistence-modernization.md](active/TP-20261003-001-rsassistant-persistence-modernization.md) |
| TP-20261004-002 | Performance Visibility and Growth History | Ready | High | [active/TP-20261004-002-performance-visibility.md](active/TP-20261004-002-performance-visibility.md) |
| TP-20261003-012 | Parsing and Runtime Cleanup | Draft | Normal | [active/TP-20261003-012-parsing-runtime-cleanup.md](active/TP-20261003-012-parsing-runtime-cleanup.md) |

## Completed

| Packet ID | Title | Status | Canonical packet |
| --- | --- | --- | --- |
| TP-20261004-001 | Performance History Capture | Complete | [completed/TP-20261004-001-performance-history-capture.md](completed/TP-20261004-001-performance-history-capture.md) |
| TP-20261003-009 | Excel Runtime Retirement | Complete | [completed/TP-20261003-009-excel-retirement.md](completed/TP-20261003-009-excel-retirement.md) |
| TP-20261003-010 | Decompose sql_utils.py by Domain | Complete | [completed/TP-20261003-010-sql-utils-decomposition.md](completed/TP-20261003-010-sql-utils-decomposition.md) |
| TP-20261003-011 | Decompose on_message.py into Services | Complete | [completed/TP-20261003-011-on-message-decomposition.md](completed/TP-20261003-011-on-message-decomposition.md) |
| TP-20261003-002 | Establish a Full CI Baseline | Complete | [completed/TP-20261003-002-ci-baseline.md](completed/TP-20261003-002-ci-baseline.md) |
| TP-20261003-003 | Establish the SQLite Runtime Foundation | Complete | [completed/TP-20261003-003-sqlite-runtime-foundation.md](completed/TP-20261003-003-sqlite-runtime-foundation.md) |
| TP-20261003-004 | Move Order Runtime State to SQLite | Complete | [completed/TP-20261003-004-order-runtime-sqlite.md](completed/TP-20261003-004-order-runtime-sqlite.md) |
| TP-20261003-005 | Move Split Monitor State to SQLite | Complete | [completed/TP-20261003-005-split-monitor-sqlite.md](completed/TP-20261003-005-split-monitor-sqlite.md) |
| TP-20261003-006 | Establish the Current Holdings SQL Contract | Complete | [completed/TP-20261003-006-holdings-sql-contract.md](completed/TP-20261003-006-holdings-sql-contract.md) |
| TP-20261003-007 | Make SQLite the Operational Holdings Read Source | Complete | [completed/TP-20261003-007-holdings-authority-inversion.md](completed/TP-20261003-007-holdings-authority-inversion.md) |
| TP-20261004-008 | Make OrderHistory Authoritative and Demote Order CSV | Complete | [completed/TP-20261004-008-orderhistory-authority.md](completed/TP-20261004-008-orderhistory-authority.md) |

## Archived / Historical

| Packet ID | Title | Status | Historical source | Canonical wrapper |
| --- | --- | --- | --- | --- |
| TP-20260612-001 | Legacy RSAssistant Hardening Train (00–09) | Superseded | `docs/task-packets/rsassistant-hardening/` | [archived/TP-20260612-001-legacy-rsassistant-hardening-train.md](archived/TP-20260612-001-legacy-rsassistant-hardening-train.md) |

## Legacy packet location

`docs/task-packets/rsassistant-hardening/` predates this canonical system. Its files are retained for design history and may contain useful implementation details, but they are **not executable source-of-truth packets**.

Do not add new packets to that directory.
