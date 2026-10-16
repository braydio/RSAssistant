# TP-20261016-002: Reconcile deployed history and pin production sources

**Packet ID:** TP-20261016-002  
**Status:** In Progress  
**Created:** 2026-10-16  
**Last updated:** 2026-10-16  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261016-002-baseline-reconciliation-and-deployment-lock.md`  
**Workstream size:** One independently testable implementation packet  
**Priority:** P0  
**Depends on:** TP-20261016-001; HUMAN local/remote history gate  
**Authoring chat:** not-recorded  
**Expected packet count / order:** 16 consecutive packets, TP-20261016-002 is #2; roadmap: `docs/architecture-overhaul-roadmap.md`.

## Objective
Reconcile deployed history and pin production sources. Preserve current production behavior unless the scoped acceptance criteria and required gates have been satisfied. Any live trading cutover is outside this packet unless explicitly specified.

## Current evidence and source boundary
Operator-reported local live HEAD 83a6b00, fork 110439c, schema v10; remote main at authoring still 221c21d. Nested auto-rsa is gitignored and bind-mounted; AutoRSA-GUI.local has uncommitted Chase/Fennel/Wells Fargo edits; remote production branch abandoned. docker compose builds dirty working tree and no regular backups.

**Important:** GitHub main at authoring was `221c21d`, while operator-reported production local `83a6b00` was unpushed. These facts are not equivalent. Do not implement on stale assumptions.

## Hard prerequisite / required refresh gate
**HUMAN + REFRESH REQUIRED: owner/local agent must reconcile local deployed 83a6b00 and remote 221c21d + this roadmap commit; no force push. Confirm v10 split-intent tables and TP-20261013-001/002 completion on resulting main. Verify an actual checkpoint and restore, then recheck these file paths.**

The implementer must mark this packet `In Progress` in `TRACKER.md` and `INDEX.md` **only after** reviewing dependency completion summaries and confirming the named files/symbols on the *then-current* canonical main. If drift changes SQL/IPC/trading semantics, refresh packet and record rationale before execution. No executing `Draft` or `Blocked`.

## Exact target files and symbols
- `docker-compose.yml`
- `Dockerfile`
- `entrypoint.sh`
- `AGENTS.md`
- `docs/task-packets/TRACKER.md`
- `docs/task-packets/INDEX.md`
- `scripts/migration_checkpoint.py`
- `.github/workflows/ci.yml`
- `rsassistant/persistence/schema.py`

## Required implementation, in order
1. On LOCAL host, run checkpoint inspect, backup and verify against volumes/db/rsa_database.db; record checksum/manifest OUTSIDE repo with mode 0600; test restore into disposable directory and verify expected open watches/account marks. Back up .env/creds separately in an encrypted restricted store, never commit.
2. Inventory git show/status of RSAssistant, nested auto-rsa and both GUI copies; preserve dirty Chase/Fennel/Wells Fargo changes on a dedicated local branch or bundle before modifying them. Compare local 83a6b00 with remote HEAD, then merge/rebase with explicit reviewed resolution. Never force main or erase local commits.
3. Pin nested auto-rsa revision via a deliberate submodule/vendor strategy and immutable build context; remove untracked runtime source bind-mount from production only after parity. Tag both baseline commits, add revision labels, image metadata and matching pre-deploy check.
4. Replace redocker-from-working-tree with script that rejects dirty tree/unknown commit, confirms verified DB backup/rollback artifact and prints deployment diff; do not change production update policies until tested.
5. Update remote tracker statuses of completed TP-20261013-001/002 only after their commits and tests really appear in canonical merged main, not simply because local report says deployed.

### Invariants / validation boundaries
- No brokerage command may be presumed filled from Discord send alone; preserve reported status and provenance.
- Do not resurrect auto-buys for old events when replaying stale or missing evidence; preserve the split-event durable claim from TP-20261013-001.
- New state belongs to canonical SQLite; legacy JSON/CSV may be fixtures or transitional input only.
- Tests must use temporary databases and mock broker transport. No live order, no credential dump, no production DB fixtures.
- Preserve original open split watches and all unresolved position/order evidence, including BTOC/KNDI/FRGT/OBAI if still outstanding at execution time.
- Include one reversible data migration strategy when schema changes and a downgrade/rollback note in the completion summary.

## Focused and full validation
- `git merge-base --is-ancestor <baseline> main`
- `python scripts/migration_checkpoint.py inspect --source volumes/db/rsa_database.db`
- `python scripts/migration_checkpoint.py backup --source volumes/db/rsa_database.db --dest ~/.rsa-backups/checkpoints`
- `python scripts/migration_checkpoint.py verify --backup <generated-file>`
- `docker compose config (offline, no docker compose up)`
- `python -m unittest discover -s unittests -p '*_test.py'`
- `python -m compileall -q rsassistant utils unittests scripts`
- Production acceptance requires an operator-reviewed read-only parity report; record exact timestamps, source versions and unknowns.

## Acceptance criteria
- [ ] Local and GitHub main agree on reviewed history and schema
- [ ] Automatic migration backups verified with real disposable restore
- [ ] Auto-rsa source revision pinned and GUI edits preserved
- [ ] No dirty-working-tree production builds and no unexpected live orders
- [ ] No regression to event idempotency, existing broker order queues or account historical data.
- [ ] Completion summary describes coverage, schema/backfill, observed runtime differences and any remaining human review.

## Explicit non-goals
Do not change trade strategy, submit orders, restart containers without a production window, drop uncommitted GUI changes, rewrite brokerage APIs or deploy experimental adapters.

## Handoff / completion report
On verified completion move exactly this canonical file from `active/` to `completed/`, update `INDEX.md` and `TRACKER.md` atomically, and write `docs/task-packets/summaries/TP-20261016-002-SUMMARY.md` (Outcome, Validation, Process Feedback, Next Handoff). State next packet TP-20261016-003 and whether a fresh planning review is required; never claim production parity from mocks only.

## Progress log (2026-10-16, local host)
Done: merged `origin/main` (867cb72) into deployed local `main` with no history rewrite (221c21d, 83a6b00, 867cb72 all ancestors of HEAD); baseline tags `baseline/rsassistant-deployed-83a6b00` and `baseline/auto-rsa-deployed-110439c` (local, unpushed); real checkpoint `~/.rsa-backups/checkpoints/rsa-checkpoint-20261016T213903Z-68c12f4c.*` (mode 0600) verified and restored into a disposable dir (integrity ok; 4 `buying` split watches BTOC/FRGT/KNDI/OBAI preserved; 246 accounts, 1198 orders); AutoRSA-GUI.local tracked edits (chase/fennel/wellsfargo) preserved as patch + file copies in `~/.rsa-backups/gui-preserve-20261016/`; `scripts/safe_deploy.sh` rejects dirty tree / stale unverified backup, dry-run by default. Tests 224 OK, compileall OK, `docker compose config` OK.
Remaining: encrypted `.env`/`creds` store (needs owner passphrase decision); image revision labels (`org.rsa.git-rev`) and `GIT_REV` build arg; pin auto-rsa via submodule/vendor and drop `./auto-rsa/src` bind mount after parity (production window); push of merged main (owner decision); checkpoint tool leaves stray `*.partial-shm/-wal` files; mark 002 Complete only after those.
