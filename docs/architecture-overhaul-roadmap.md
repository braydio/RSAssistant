# RSAssistant + auto-rsa unification: implementation roadmap (2026-10-16)

**Canonical plan:** `docs/task-packets/INDEX.md` / `TRACKER.md` govern execution. This is a sequencing overview, not an executable packet.
**Target:** one application, canonical SQLite, a typed local worker boundary, **RSAssistant-native broker integration SDK and owned adapters**, and a staged retirement of auto-rsa's broker execution dependency. Preserve GPLv3/vendor attributions and assess compatibility before redistribution.

## Current decision (2026-10-16): native broker integrations

**End state:** RSAssistant-owned `BrokerAdapter` SDK, native per-broker implementations using supported official interfaces, reviewed SDKs or independently authored browser clients as necessary. NelsonDane auto-rsa remains a **pinned legacy bridge only** until each required broker is independently migrated and TP-018 verifies that all order, position, activity, recovery and rollback capabilities can operate without it. Details: [native brokerage strategy](native-brokerage-strategy.md).

**Deployment facts:** GitHub `main@7db0012` at authoring; user reports five later **local-only** commits through `39c0e5b` not pushed or deployed. Current live schema remains v10 and old image per user. These packet amendments are staged on a planning branch, NOT automatically merged into main and do not authorize a production window. Locally completed Restic/policy/hold fixes must be reconciled before implementation of new packets.

**Prior completed work preserved:** TP-008 typed IPC, TP-003 holdings, TP-004 order intents, TP-005 identities and TP-006 connection health are foundations, not work to repeat. Native snapshot adapters do not count as live broker APIs. The goal does not require rewriting all 16 listed brokers; prioritize used accounts and explicitly disable or retain narrow legacy fallback for others.

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

## Updated execution train (18 immutable packet IDs)

The numeric ID records creation order; **TP-017 executes before TP-009** and **TP-018 executes after TP-011**, because both were authored after the original 16 packets. Treat the following as dependency order, not permission to execute `Draft` or `In Progress` packets without their human/refresh gates. Status reflects GitHub `main@7db0012` at this planning refresh, not the user's unpushed host work.

| Order | Packet | Workstream | Status | Gate / dependency |
| --- | --- | --- | --- | --- |
| 01 | TP-20261016-001 | Safe SQLite backup tooling | Complete | Operational Restic + restore still pending |
| 02 | TP-20261016-002 | Encrypted backup, pinned legacy source, guarded deploy | In Progress | Restic, local 39c0e5b reconcile, safe liquidate and execution hold |
| 03 | TP-20261016-003 | Holdings import and parity | Complete | Live parity verified in operator's report |
| 04 | TP-20261016-004 | Order intents, receipts and fills | Complete | Historical unknowns remain for broker reconciliation |
| 05 | TP-20261016-005 | Canonical account identities | Complete | Alias mapping preserved |
| 06 | TP-20261016-006 | Broker health / incident registry | Complete | No live broker changes |
| 07 | TP-20261016-007 | Guided secure reauthentication | In Progress | Live integration, profile-level enforcement / user review |
| 08 | TP-20261016-008 | Typed broker worker IPC and shadow mode | Complete | Reuse contract unchanged |
| **08A** | **TP-20261016-017** | **Native Adapter SDK, capability registry, source routing** | **Draft** | **REFRESH after 002/007 local code and 008 interface; no live orders** |
| 09 | TP-20261016-009 | Native Fidelity adapter, read-only parity & activity | In Progress | 017; broker sessions and historical execution hold review |
| 10 | TP-20261016-010 | Native Fennel, Public and Robinhood adapters | In Progress | 017/009; Fennel 429, Public historic sells, session parity |
| 11 | TP-20261016-011 | Native other brokers by proven use | Draft | 010 + native SDK; preserve GUI patches |
| **11A** | **TP-20261016-018** | **Broker-by-broker native cutover, rollback, upstream egress** | **Draft** | **002/007/009/010/011/017; HUMAN live-canary and broker-evidence gates** |
| 12 | TP-20261016-012 | Strict split-policy evidence / discovery | In Progress | New policy applied local-only per operator; no auto-trading expansion |
| 13 | TP-20261016-013 | Corporate action credit/sale reconciliation | Draft | Broker-originated activity / fills from 004/009/010/012 |
| 14 | TP-20261016-014 | Unified `/rs` operator commands | In Progress | Canonical service contracts; no old direct trade side effects |
| 15 | TP-20261016-015 | Evidence-backed net P&L and exceptions | In Progress | Missing fills stay unknown, not zero |
| 16 | TP-20261016-016 | Final legacy retirement and dead-code cleanup | Draft | **018 plus existing packet gates and explicit owner cutover** |

TP-012–015 can advance alongside native adapters wherever they depend only on proven canonical data services, but must not imply broker activity is available when adapters still report UNSUPPORTED. Keep original canonical statuses unless an implementation summary verifies completion.

## Release strategy

- Phase 0 safety: packet 001 then local-state/histories gate 002.
- Phase 1 correctness: packets 003–005. Keep existing live bot, preserve position/order history.
- Phase 2 broker reliability: 006–007. Structured health/incident records, read-only recovery first.
- Phase 3 integration: 008 Complete; 017 foundation (Draft) before 009/010/011 native broker clients, owned API + isolated legacy fallback. TP-018 validates phased cutover and removes each broker's upstream path only after proven parity.
- Phase 4 product: 012–015. Complete action lifecycle, evidence-backed operator UX/reporting.
- Phase 5 removal: 016 only after 018, broker activity reconciliation, rollback rehearsal and explicit owner cutover. Remaining optional brokers may stay in a documented, separately pinned legacy compatibility worker; do not falsely claim zero dependency.
- At every milestone: backup + verify, run focused and full CI, record DB schema/data parity and exceptions, pause automated **new** trading where outcome is ambiguous without suppressing reconciliation.

## Known stop conditions

Missing/unknown broker order ID for an apparently sent order; inability to reconcile a pre-existing split position; source snapshot freshness discrepancy; migration attempts against dirty/unpushed production worktree; exposed credentials in diagnostics; database migration without restorable backup; testing against production DB. Any of these blocks cutover; unresolved trades require operator reconciliation, not guessed fixes.

## Canonical documents

- Packet index: `docs/task-packets/INDEX.md`
- Live dependency ledger: `docs/task-packets/TRACKER.md`
- Repo rules: `AGENTS.md`
- Implementation summaries: `docs/task-packets/summaries/TP-*-SUMMARY.md`
- First preflight utility: `scripts/migration_checkpoint.py`

## Native adapter decision acceptance

- Maintain **one local API and capability registry** even when upstream broker remote interfaces differ. Prefer official APIs; independently develop native clients where permitted and technically necessary. No requirement to clone NelsonDane's implementation.
- Each required broker must offer independently observed positions and order/activity evidence, not merely JSON-to-SQL shadow parity; unknown fill means order remains blocked and unverified.
- Do not copy GPL auto-rsa source into MIT RSAssistant without licensing review; IPC alone does not guarantee license separation.
- Respect user-described rollout gates: local Restic encrypted backup and restore, safe bare-liquidate preview, ambiguous-order dispatch hold, pinned source, existing old production unaffected, and explicit future deployment authorization.
