# Task Packet Index

Canonical packet discovery index for `braydio/RSAssistant`.

See [README.md](README.md) for naming, lifecycle, execution, persistence, and authoring rules. See [TRACKER.md](TRACKER.md) for live execution state.

## Active

| Packet ID | Title | Status | Priority | Canonical packet |
| --- | --- | --- | --- | --- |
| TP-20261003-001 | RSAssistant Persistence Modernization and Decomposition | Ready | High | [active/TP-20261003-001-rsassistant-persistence-modernization.md](active/TP-20261003-001-rsassistant-persistence-modernization.md) |
| TP-20261003-002 | CI Baseline Completion | Ready | High | [active/TP-20261003-002-ci-baseline-completion.md](active/TP-20261003-002-ci-baseline-completion.md) |
| TP-20261003-003 | SQLite Runtime Foundation Completion | Draft | High | [active/TP-20261003-003-sqlite-runtime-foundation.md](active/TP-20261003-003-sqlite-runtime-foundation.md) |
| TP-20261003-004 | Order Runtime Persistence Completion | Draft | High | [active/TP-20261003-004-order-runtime-sqlite.md](active/TP-20261003-004-order-runtime-sqlite.md) |
| TP-20261003-005 | Split Monitor Persistence to SQLite | Draft | High | [active/TP-20261003-005-split-monitor-sqlite.md](active/TP-20261003-005-split-monitor-sqlite.md) |
| TP-20261003-006 | Holdings SQL Contract v2 | Draft | High | [active/TP-20261003-006-holdings-sql-contract-v2.md](active/TP-20261003-006-holdings-sql-contract-v2.md) |
| TP-20261004-001 | Performance History Capture | Draft | High | [active/TP-20261004-001-performance-history-capture.md](active/TP-20261004-001-performance-history-capture.md) |
| TP-20261003-007 | Holdings Authority Inversion | Draft | High | [active/TP-20261003-007-holdings-authority-inversion.md](active/TP-20261003-007-holdings-authority-inversion.md) |
| TP-20261004-002 | Performance Visibility and Growth History | Draft | High | [active/TP-20261004-002-performance-visibility.md](active/TP-20261004-002-performance-visibility.md) |
| TP-20261003-008 | OrderHistory Authority and CSV Demotion | Draft | Normal | [active/TP-20261003-008-order-history-authority.md](active/TP-20261003-008-order-history-authority.md) |
| TP-20261003-009 | Excel Runtime Retirement | Draft | Normal | [active/TP-20261003-009-excel-retirement.md](active/TP-20261003-009-excel-retirement.md) |
| TP-20261003-010 | Decompose sql_utils.py by Domain | Draft | Normal | [active/TP-20261003-010-sql-utils-decomposition.md](active/TP-20261003-010-sql-utils-decomposition.md) |
| TP-20261003-011 | Decompose on_message.py into Services | Draft | Normal | [active/TP-20261003-011-on-message-decomposition.md](active/TP-20261003-011-on-message-decomposition.md) |
| TP-20261003-012 | Parsing and Runtime Cleanup | Draft | Normal | [active/TP-20261003-012-parsing-runtime-cleanup.md](active/TP-20261003-012-parsing-runtime-cleanup.md) |

## Completed

None in the canonical system yet.

## Archived / Historical

| Packet ID | Title | Status | Historical source | Canonical wrapper |
| --- | --- | --- | --- | --- |
| TP-20260612-001 | Legacy RSAssistant Hardening Train (00–09) | Superseded | `docs/task-packets/rsassistant-hardening/` | [archived/TP-20260612-001-legacy-rsassistant-hardening-train.md](archived/TP-20260612-001-legacy-rsassistant-hardening-train.md) |

## Legacy packet location

`docs/task-packets/rsassistant-hardening/` predates this canonical system. Its files are retained for design history and may contain useful implementation details, but they are **not executable source-of-truth packets**.

Do not add new packets to that directory.
