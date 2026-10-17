# TP-20261016-005: Canonical broker accounts with non-destructive alias resolution

**Packet ID:** TP-20261016-005  
**Status:** Complete
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261016-005-canonical-account-identity.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-003 and -004  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-005 is #5; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Canonical broker accounts with non-destructive alias resolution. Preserve current production behavior unless the scoped acceptance criteria and required gates have been satisfied. Any live trading cutover is outside this packet unless explicitly specified.

## Current evidence and source boundary
Operator report: 225 Accounts rows vs ~38 active, inconsistent casing/labels and historical-only records. Fidelity/Chase/Fennel aliases differ between order parsing and holdings snapshot.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These facts are not equivalent. Do not implement on stale assumptions.

## Hard prerequisite / required refresh gate
**REFRESH REQUIRED: inspect live Accounts, account_mappings and new receipt/holdings account references; obtain broker account identity evidence. Last-four matching alone is not enough.**

The implementer must mark this packet `In Progress` in `TRACKER.md` and `INDEX.md` **only after** reviewing dependency completion summaries and confirming the named files/symbols on the *then-current* canonical main. If drift changes SQL/IPC/trading semantics, refresh packet and record rationale before execution. No executing `Draft` or `Blocked`.

## Exact target files and symbols
- `rsassistant/persistence/accounts.py`
- `rsassistant/persistence/schema.py`
- `rsassistant/persistence/holdings.py`
- `rsassistant/persistence/orders.py`
- `utils/config_utils.py`
- `utils/parsing_utils.py`
- `scripts/cleanup_accounts.py (local-only until 002)`
- `unittests/persistence_import_contract_test.py`

## Required implementation, in order
1. Add canonical_account_id opaque UUID and account_aliases(broker_id, login_profile_id, normalized_label, evidence_source, verified, observed_at, canonical_account_id), with UNIQUE scope on verified aliases and no destructive change to historic IDs.
2. Build deterministic normalization of broker case and display aliases; never merge accounts on last4 alone. For conflicting evidence emit resolution queue requiring operator choice; record provenance and preserve original labels encrypted/hidden where necessary.
3. Create mapping table legacy_account_id -> canonical_account_id and migrate foreign keys in phases with backfill, query parity and rollback. Don't delete historical accounts while upgrading code.
4. Expose read-only mapping report with counts by broker: active, ambiguous, historical-only and test fixtures. Add explicit operator 'resolve conflict' command only after UI authority checks.
5. After snapshots/order-fills match, archive truly unreferenced test records in controlled transaction; leave unknown legacy history intact.

### Invariants / validation boundaries
- No brokerage command may be presumed filled from Discord send alone; preserve reported status and provenance.
- Do not resurrect auto-buys for old events when replaying stale or missing evidence; preserve the split-event durable claim from TP-20261013-001.
- New state belongs to canonical SQLite; legacy JSON/CSV may be fixtures or transitional input only.
- Tests must use temporary databases and mock broker transport. No live order, no credential dump, no production DB fixtures.
- Preserve original open split watches and all unresolved position/order evidence, including BTOC/KNDI/FRGT/OBAI if still outstanding at execution time.
- Include one reversible data migration strategy when schema changes and a downgrade/rollback note in the completion summary.

## Focused and full validation
- `python -m unittest unittests.accounts_test (add) unittests.persistence_import_contract_test`
- `two accounts share last4, casing, login-profile aliases, multiple historic labels, idempotent migration and rollback`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Production acceptance requires an operator-reviewed read-only parity report; record exact timestamps, source versions and unknowns.

## Acceptance criteria
- [ ] One verified canonical identity per active account with no last4 collision
- [ ] All existing historical/order/split-account references retained
- [ ] Ambiguous matches visible and not silently merged
- [ ] Only proven fixture rows removable by explicit operation
- [ ] No regression to event idempotency, existing broker order queues or account historical data.
- [ ] Completion summary describes coverage, schema/backfill, observed runtime differences and any remaining human review.

## Explicit non-goals
No credential copying or live position trades, no blanket deletion of dormant broker accounts.

## Handoff / completion report
On verified completion move exactly this canonical file from `active/` to `completed/`, update `INDEX.md` and `TRACKER.md` atomically, and write `docs/task-packets/summaries/TP-20261016-005-SUMMARY.md` (Outcome, Validation, Process Feedback, Next Handoff). State next packet TP-20261016-006 and whether a fresh planning review is required; never claim production parity from mocks only.
