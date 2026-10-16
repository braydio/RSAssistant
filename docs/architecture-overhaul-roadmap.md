# RSAssistant + auto-rsa unification: implementation roadmap (2026-10-16)

**Canonical plan:** `docs/task-packets/INDEX.md` / `TRACKER.md` govern execution. This is a sequencing overview, not an executable packet.
**Target:** one application, one operator surface, canonical SQLite state, a separately isolatable brokerage worker, typed broker events instead of Discord text/JSON side channels. Preserve the existing GPLv3 auto-rsa notices and assess compatibility before redistributing unified code.

## Evidence and baseline

- **Remote GitHub main checked 2026-10-16:** `221c21d26f1e03c2278a9b67b278f9ffe4832dc4`. It still reports TP-20261013-001/002 as Ready and migration 9.
- **Operator's local production report, 2026-10-16:** production working-tree `83a6b00` with schema v10, completed TP-20261013-001/002, yfinance and importer fixes, not pushed. These are **operator-reported local facts**, not verified by this GitHub connection. **Do not run code-changing successor packets until the histories are reconciled without force-push or discarded local work.**
- Historic outbound command sends outnumber broker-verified fills; Fidelity acknowledgements are ambiguous, and held positions have conflicted across JSON/SQL/CSV. No command acknowledgement is a fill.
- Active split watch/account marks for BTOC/KNDI/FRGT/OBAI and all pending/unknown orders must survive.
- Local `auto-rsa/` is a gitignored nested repository and its `src` directory is bind-mounted. Additional GUI forks have uncommitted Chase/Fennel/Wells Fargo changes that require preservation.
- Existing baseline: Python 3.12 RSAssistant, Python 3.14 auto-rsa, two Discord bots, shared rw volume, no automated consistent SQLite backups.

## Architectural invariants

1. **No duplicate trades:** immutable event identity `(ticker,effective_date)`, durable per-account order intents, atomic claims, no re-submission of unknown outcomes.
2. **Broker source of truth:** actual broker order IDs/fills and time-stamped position/activity snapshots; an unavailable quote means unknown price, not a synthetic fill at $0.
3. **One writer per domain:** SQLite operational authority; JSON/CSV temporary import/export. Cross-process worker talks through typed authenticated local IPC, never directly modifies application tables.
4. **Stable accounts:** internal UUID + aliases/evidence, avoid last-four-only collisions and preserve historical identity and live split marks.
5. **Connection recovery:** health per login profile, classified failures, bounded retry, secure MFA, broker-specific circuit breakers; never disclose tokens/OTP, cookies, page dumps or account IDs in Discord.
6. **Deployment safety:** versioned images, pin broker source, explicit migration backup and rollback, never build unreviewed dirty working tree into production.
7. **No trading side effects from tests, healthchecks, data migration, status commands or backfill.** Paper/offline fixtures first; live canary requires human approval.
8. **Preserve third-party licenses** (auto-rsa GPLv3; RSAssistant MIT; separate vendor licenses) and original attributions.

## Consecutive task-packet train

| Order | Packet | Outcome | Status at authoring | Mandatory handoff / refresh gate |
|---|---|---|---|---|
| 1 | TP-20261016-001 | WAL-consistent backup and read-only preflight | Complete (code + isolated tests; no live execution) | Run on production before any migration |
| 2 | TP-20261016-002 | Reconcile local deployed history, freeze inputs and pin deployment | Blocked | **HUMAN LOCAL GATE**: import unpushed commits, account for nested fork/GUI edits; recut downstream against resulting main |
| 3 | TP-20261016-003 | Restore one trustworthy holdings ingest | Draft | **REFRESH** importer seams/production snapshots after 002; prove fresh Fidelity import |
| 4 | TP-20261016-004 | Order acknowledgement/fill reconciliation | Draft | **REFRESH** against local `83a6b00` fix and broker activity; no replay of historical sends |
| 5 | TP-20261016-005 | Canonical account identity and alias mapping | Draft | **REFRESH** after 003/004 account evidence stabilized |
| 6 | TP-20261016-006 | Connection incident registry + broker health contract | Draft | 005 identities required; scoped read-only checks |
| 7 | TP-20261016-007 | Guided authentication and self-recovery | Draft | **REFRESH** MFA requirements/secure UI controls; no codes in Discord |
| 8 | TP-20261016-008 | Typed worker IPC and order dispatcher contract | Draft | **REFRESH** 004/006 correctness; dual path shadow mode only |
| 9 | TP-20261016-009 | Fidelity adapter canary | Draft | **HUMAN GATE** broker-order history, user approval for any live canary |
| 10 | TP-20261016-010 | Fennel, Public, Robinhood migration | Draft | **REFRESH** 009 interface; account/429/empty holdings evidence |
| 11 | TP-20261016-011 | Wells Fargo, Schwab, Chase, SoFi, Webull and other brokers | Draft | **REFRESH** actual broker priorities, preserved GUI edits and driver tests |
| 12 | TP-20261016-012 | Consolidated split-policy provenance and discovery | Draft | 004/005/008 event identity & account capabilities; no nearest-whole-as-up |
| 13 | TP-20261016-013 | Corporate action credit and sell reconciliation | Draft | **REFRESH** real broker activity/cash-in-lieu evidence |
| 14 | TP-20261016-014 | Unified `/rs` commands and dashboard service | Draft | 008/012/013 APIs stabilized; aliases cannot trade on deprecated paths |
| 15 | TP-20261016-015 | Realized P&L, historical backfill, exception digests | Draft | **REFRESH** source completeness; unknown ≠ zero |
| 16 | TP-20261016-016 | Legacy deletion, cutover, deployment and rollback | Draft | **HUMAN CUTOVER GATE** all brokers reconciled and recovery/rollback rehearsed |

**Execution rule:** Packet N is not authorized merely because packet N-1 completed. Every successor checks its named acceptance criteria; a REFRESH or HUMAN gate must be recorded in tracker and packet before changing production behavior. Never execute Draft or Blocked packets without refreshing to Ready. `TP-20261003-012` remains a separate historical Draft; reconcile overlap with the final cleanup packet.

## Release strategy

- Phase 0 safety: packet 001 then local-state/histories gate 002.
- Phase 1 correctness: packets 003–005. Keep existing live bot, preserve position/order history.
- Phase 2 broker reliability: 006–007. Structured health/incident records, read-only recovery first.
- Phase 3 integration: 008–011. Worker adapters, dual-read/shadow, one broker at a time.
- Phase 4 product: 012–015. Complete action lifecycle, evidence-backed operator UX/reporting.
- Phase 5 removal: 016. Disable old paths only after rollback test and per-broker parity.
- At every milestone: backup + verify, run focused and full CI, record DB schema/data parity and exceptions, pause automated **new** trading where outcome is ambiguous without suppressing reconciliation.

## Known stop conditions

Missing/unknown broker order ID for an apparently sent order; inability to reconcile a pre-existing split position; source snapshot freshness discrepancy; migration attempts against dirty/unpushed production worktree; exposed credentials in diagnostics; database migration without restorable backup; testing against production DB. Any of these blocks cutover; unresolved trades require operator reconciliation, not guessed fixes.

## Canonical documents

- Packet index: `docs/task-packets/INDEX.md`
- Live dependency ledger: `docs/task-packets/TRACKER.md`
- Repo rules: `AGENTS.md`
- Implementation summaries: `docs/task-packets/summaries/TP-*-SUMMARY.md`
- First preflight utility: `scripts/migration_checkpoint.py`
