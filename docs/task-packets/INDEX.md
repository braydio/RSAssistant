# Task Packet Index

Canonical packet discovery index for `braydio/RSAssistant`.

See [README.md](README.md) for naming, lifecycle, persistence, and authoring rules. See [TRACKER.md](TRACKER.md) for live execution state.

## 2026-10-16: Unified overhaul (canonical consecutive train)

**2026-10-16 baseline divergence:** GitHub main at authoring `221c21d` is behind operator-reported deployed local `83a6b00`; historical TP-20261013-001/002 statuses below describe the remote checkout, *not* the operator's locally completed work. TP-20261016-002 must reconcile history and update old statuses before successor execution. New packets are not permission for live trading; read `docs/architecture-overhaul-roadmap.md`.

| Order | Packet ID | Title | Status | Canonical packet |
| --- | --- | --- | --- | --- |
| 1 | TP-20261016-001 | Reproducible migration checkpoint and safe SQLite backup | Complete | [completed/TP-20261016-001-migration-checkpoint.md](completed/TP-20261016-001-migration-checkpoint.md) |
| 2 | TP-20261016-002 | Reconcile deployed history and pin production sources | In Progress | [active/TP-20261016-002-baseline-reconciliation-and-deployment-lock.md](active/TP-20261016-002-baseline-reconciliation-and-deployment-lock.md) |
| 3 | TP-20261016-003 | Verify and restore canonical holdings ingestion | Complete | [completed/TP-20261016-003-holdings-single-writer-integrity.md](completed/TP-20261016-003-holdings-single-writer-integrity.md) |
| 4 | TP-20261016-004 | Recover order acknowledgement and broker fill provenance | Complete | [completed/TP-20261016-004-order-receipts-and-fill-reconciliation.md](completed/TP-20261016-004-order-receipts-and-fill-reconciliation.md) |
| 5 | TP-20261016-005 | Canonical broker accounts with non-destructive alias resolution | Complete | [completed/TP-20261016-005-canonical-account-identity.md](completed/TP-20261016-005-canonical-account-identity.md) |
| 6 | TP-20261016-006 | Broker connection health contract and incident registry | Complete | [completed/TP-20261016-006-broker-connection-health-incidents.md](completed/TP-20261016-006-broker-connection-health-incidents.md) |
| 7 | TP-20261016-007 | Secure guided reauthentication and bounded recovery | In Progress | [active/TP-20261016-007-guided-broker-reauth-and-recovery.md](active/TP-20261016-007-guided-broker-reauth-and-recovery.md) |
| 8 | TP-20261016-008 | Direct typed broker worker bridge and shadow orchestration | Complete | [completed/TP-20261016-008-typed-broker-worker-ipc.md](completed/TP-20261016-008-typed-broker-worker-ipc.md) |
| 9 | TP-20261016-009 | Extract and shadow-validate the Fidelity broker adapter | In Progress | [active/TP-20261016-009-fidelity-adapter-shadow-canary.md](active/TP-20261016-009-fidelity-adapter-shadow-canary.md) |
| 10 | TP-20261016-010 | Migrate Fennel, Public and Robinhood through the typed worker | In Progress | [active/TP-20261016-010-active-broker-adapters.md](active/TP-20261016-010-active-broker-adapters.md) |
| 11 | TP-20261016-011 | Preserve and selectively migrate remaining broker connections | Draft | [active/TP-20261016-011-secondary-broker-adapters.md](active/TP-20261016-011-secondary-broker-adapters.md) |
| 12 | TP-20261016-012 | Unify split discovery and fractional-share evidence | In Progress | [active/TP-20261016-012-split-discovery-policy-provenance.md](active/TP-20261016-012-split-discovery-policy-provenance.md) |
| 13 | TP-20261016-013 | Account-level split credits, cash-in-lieu and sale reconciliation | Draft | [active/TP-20261016-013-corporate-action-settlement-reconciliation.md](active/TP-20261016-013-corporate-action-settlement-reconciliation.md) |
| 14 | TP-20261016-014 | Replace scattered commands with one typed operator interface | Draft | [active/TP-20261016-014-unified-command-surface.md](active/TP-20261016-014-unified-command-surface.md) |
| 15 | TP-20261016-015 | Evidence-grade performance reporting and exception monitoring | Draft | [active/TP-20261016-015-realized-pnl-and-exception-digests.md](active/TP-20261016-015-realized-pnl-and-exception-digests.md) |
| 16 | TP-20261016-016 | Retire redundant bots and dead code after verified migration | Draft | [active/TP-20261016-016-legacy-retirement-and-cutover.md](active/TP-20261016-016-legacy-retirement-and-cutover.md) |

## Active

| Packet ID | Title | Status | Priority | Canonical packet |
| --- | --- | --- | --- | --- |
| TP-20261003-001 | RSAssistant Persistence Modernization and Decomposition | In Progress | High | [active/TP-20261003-001-rsassistant-persistence-modernization.md](active/TP-20261003-001-rsassistant-persistence-modernization.md) |
| TP-20261003-012 | Parsing and Runtime Cleanup | Draft | Normal | [active/TP-20261003-012-parsing-runtime-cleanup.md](active/TP-20261003-012-parsing-runtime-cleanup.md) |

## Resource optimization train (2026-10-10)

| Packet ID | Title | Status | Priority | Canonical packet |
| --- | --- | --- | --- | --- |

## Completed

| Packet ID | Title | Status | Canonical packet |
| --- | --- | --- | --- |
| TP-20261013-002 | Codex Error Watcher: Fail-Closed Diagnostics + Bounded State | Complete | [completed/TP-20261013-002-codex-error-watcher-sandbox-output-hardening.md](completed/TP-20261013-002-codex-error-watcher-sandbox-output-hardening.md) |
| TP-20261013-001 | Split Event Lifecycle + Autobuy Idempotency | Complete | [completed/TP-20261013-001-split-event-lifecycle-and-autobuy-idempotency.md](completed/TP-20261013-001-split-event-lifecycle-and-autobuy-idempotency.md) |
| TP-20261010-011 | Consolidate Long-Sleep Order Tasks without Changing Execution Semantics | Complete | [completed/TP-20261010-011-scheduled-order-timer-consolidation.md](completed/TP-20261010-011-scheduled-order-timer-consolidation.md) |
| TP-20261010-010 | Replace Per-Ticker Holdings CSV Scans with One SQL Read | Complete | [completed/TP-20261010-010-holdings-summary-single-pass.md](completed/TP-20261010-010-holdings-summary-single-pass.md) |
| TP-20261010-009 | Stop Shipping Runtime Artifacts and Add Safe Retention | Complete | [completed/TP-20261010-009-artifact-hygiene-and-retention.md](completed/TP-20261010-009-artifact-hygiene-and-retention.md) |
| TP-20261010-008 | Lean Docker Image, Startup I/O, and Health Checks | Complete | [completed/TP-20261010-008-lean-container-startup.md](completed/TP-20261010-008-lean-container-startup.md) |
| TP-20261010-007 | ULT-MA Plugin Nonblocking Market Data and Idle Efficiency | Complete | [completed/TP-20261010-007-ultma-idle-and-async-market-data.md](completed/TP-20261010-007-ultma-idle-and-async-market-data.md) |
| TP-20261010-006 | Bound Market Price Cache and Minimize Disk Writes | Complete | [completed/TP-20261010-006-price-cache-bounds-and-atomicity.md](completed/TP-20261010-006-price-cache-bounds-and-atomicity.md) |
| TP-20261010-003 | Keep Network and Disk Operations off Discord Event Loop | Complete | [completed/TP-20261010-003-nonblocking-discord-network.md](completed/TP-20261010-003-nonblocking-discord-network.md) |
| TP-20261010-002 | Replace Threaded Scheduler with Asyncio-Native Jobs | Complete | [completed/TP-20261010-002-asyncio-native-scheduler.md](completed/TP-20261010-002-asyncio-native-scheduler.md) |
| TP-20261010-004 | Make Holdings Snapshot Import Change-Driven and Retry-Safe | Complete | [completed/TP-20261010-004-holdings-import-change-detection.md](completed/TP-20261010-004-holdings-import-change-detection.md) |
| TP-20261010-005 | Bound Logging Memory, Disk Churn, and Sensitive Payloads | Complete | [completed/TP-20261010-005-bounded-and-safe-logging.md](completed/TP-20261010-005-bounded-and-safe-logging.md) |
| TP-20261010-001 | Runtime Resource Baseline and Regression Instrumentation | Complete | [completed/TP-20261010-001-runtime-resource-baseline.md](completed/TP-20261010-001-runtime-resource-baseline.md) |
| TP-20261004-002 | Performance Visibility and Growth History | Complete | [completed/TP-20261004-002-performance-visibility.md](completed/TP-20261004-002-performance-visibility.md) |
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
