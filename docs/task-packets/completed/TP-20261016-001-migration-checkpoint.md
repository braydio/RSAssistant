# TP-20261016-001: Reproducible migration checkpoint and safe SQLite backup

**Packet ID:** TP-20261016-001
**Status:** Complete
**Created:** 2026-10-16
**Last updated:** 2026-10-16
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/completed/TP-20261016-001-migration-checkpoint.md`
**Workstream size:** One implementation packet
**Priority:** P0
**Depends on:** None (repository-only implementation). Production execution still requires owner/local access.
**Authoring chat:** not-recorded
**Expected packet count / order:** 16 consecutive packets, TP-20261016-001 through -016; overview at `docs/architecture-overhaul-roadmap.md`.

## Objective

Provide an operator-invoked, dependency-free, **read-only** SQLite inventory and **WAL-consistent** checkpoint facility before migrating live trading state. It must not import `utils.config_utils`, start the bot, apply `run_migrations`, alter tables, run live broker calls, or silently write to the production DB. A backup is a *separate explicit action*, never a consequence of an inspect/status command.

## Confirmed baseline

- `rsassistant/persistence/db.py::connect_runtime_db()` opens a normal read/write connection and `initialize_runtime_db()` applies migrations: **do not use them** in a checkpoint tool.
- `utils/config_utils.py::SQL_DATABASE` defaults to `VOLUMES_DIR/db/rsa_database.db` but configuration loading has side effects; require an explicit `--source` instead of importing config.
- `scripts/audit_runtime_artifacts.py` inspects/prunes expendable logs; it is not a DB backup, and deliberately protects database files.
- Operator's local report states schema v10, WAL, active watch state, and no scheduled backup. GitHub remote main at planning time is still `221c21d` and records v9. This packet accepts either version without applying migrations.

## Implemented files and exact contract

### `scripts/migration_checkpoint.py`

Standard-library CLI with **three subcommands**:

```bash
python scripts/migration_checkpoint.py inspect --source ./volumes/db/rsa_database.db
python scripts/migration_checkpoint.py backup --source ./volumes/db/rsa_database.db --dest "$HOME/.rsa-backups/checkpoints"
python scripts/migration_checkpoint.py verify --backup "$HOME/.rsa-backups/checkpoints/<name>.sqlite3"
```

1. `source_connection(source)`: require an existing, non-symlink regular file; open `file:...?mode=ro` and enforce `PRAGMA query_only=ON`; no fallback to creating missing DB.
2. `inventory(conn)`: `PRAGMA quick_check`, schema version and **row counts only** for known tables (`Accounts`, `holdings_current`, `HoldingsLive`, `OrderHistory`, `rsa_order_send_log`, `split_monitor`, `split_event_intents`). Never dump rows, credentials or account numbers. Only count tables present in the selected schema.
3. `git_state(root)`: identify checkout HEAD and boolean tracked-dirty state without outputting the names/content of dirty files.
4. `private_destination(dest,source)`: destination is operator-specified, not the source DB directory or a symlink; directory permissions **0700**, files **0600**. Refuse a public destination.
5. `backup(source,dest,root)`: open source read-only; use SQLite `Connection.backup()` into private `.partial` file; verify `quick_check` and schema compatibility, atomically rename to unique timestamp/nonce SQLite file; write separate JSON manifest with sha256 digest, schema/counts, Git HEAD and dirty flag. No source mutation.
6. `verify(path)`: sha256 + filename + schema/count manifest verification; explicit error on tampering.
7. `main()`: nonzero exit and descriptive sanitized error messages; no automatic cleanup of prior valid backups.

This checkpoint **does not** copy environment variables, `.env`, auth profiles or credential stores; those require separately controlled secrets backup and restore procedures. Backed-up SQLite itself is sensitive and must be protected.

### `unittests/migration_checkpoint_test.py`

Standard `unittest` fixtures using temporary synthetic SQLite WAL DB; no imports of application runtime, no production paths. Tests:
- readonly inspect refuses INSERT, database unchanged;
- WAL-consistent snapshot survives later source mutations;
- restrictive file/dir modes;
- checksum tampering detected;
- missing source never created;
- symlink, source-dir and public destination refused.

### `docs/architecture-overhaul-roadmap.md`, `docs/task-packets/INDEX.md`, `TRACKER.md`

Declare safety-first train and immutable chronology; do **not** mark a live system backup as taken.

## Validation

Executed in isolated Python 3 environment before repository write:
```bash
python -m unittest discover -s unittests -p 'migration_checkpoint_test.py' -v
python -m compileall -q scripts/migration_checkpoint.py unittests/migration_checkpoint_test.py
```
**Result:** six isolated tests passed; compileall passed. Full RSAssistant suite and live production snapshot **not run from this environment**. Remote CI may run on GitHub after commit. No user-host files modified by these checks.

## Implementation order completed

1. Inspect repo DB/config/artifact paths and packet governance.
2. Implement isolated inspection/backup/verification tool.
3. Implement synthetic SQLite WAL tests; run six focused tests and syntax check.
4. Add roadmap, first packet, completion summary, and successor packet registrations; publish together to `main`.
5. Defer any operator-host backup execution until local checkout is synchronized.

## Non-goals

No migrations, account cleanup, order/fill changes, broker logins, bot restarts, live Docker deploy, Git push of unpushed local history, database credential backup, or auto-scheduling. No claim that filesystem backup protects a broker session or that a checksum alone makes a restorable backup.

## Acceptance criteria

- [x] No application runtime import or trading side effect.
- [x] Missing DB, symlink or public destination rejected.
- [x] SQLite online backup + verification + manifest.
- [x] Tests use scratch WAL database, not production DB.
- [x] Six focused tests and syntax compilation passed.
- [ ] **Operational gate:** run `backup` and `verify` on the actual live database before schema-changing successor. Owner/local execution required.
- [ ] **Operational gate:** confirm off-host backup and restore drill, including protected `creds/`, before high-risk cutover.

## Completion report

`docs/task-packets/summaries/TP-20261016-001-SUMMARY.md` records repo changes, tests, operational limitations and required successor gate. Implementer must never reinterpret isolated tests as verified live migration readiness.
