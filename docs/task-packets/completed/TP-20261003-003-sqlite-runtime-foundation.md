# TP-20261003-003: Establish the SQLite Runtime Foundation

**Packet ID:** TP-20261003-003  
**Status:** Complete
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261003-003-sqlite-runtime-foundation.md`
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-002

## Objective

Make SQLite the always-available runtime persistence foundation, independent of the legacy `SQL_LOGGING_ENABLED` switch, and establish `rsassistant/persistence/` as the canonical home for runtime connection and schema migration helpers.

## Confirmed current state

- `utils/db/connection.py` opens SQLite with foreign keys and a 5-second busy timeout; `utils/db/migrations.py` sets WAL mode and applies versions 1–4 through `PRAGMA user_version`.
- `utils/sql_utils.py` imports those helpers, but `get_db_connection()` and most SQL domain helpers are gated by `SQL_LOGGING_ENABLED`.
- `utils/sql_utils.init_db()` skips schema setup when the flag is false, and `rsassistant/bot/core.py` skips DB initialization and watchlist loading under that same flag.
- `utils/config_utils.py` falls back to legacy account-mapping JSON and skips mapping writes when the flag is false.
- Existing tests expect tuple-style SQLite rows from `get_db_connection()`; preserve that behavior while centralizing the connection helper.

## Required changes

### `rsassistant/persistence/`

Create the package, a canonical `db.py` connection helper, and `schema.py` migrations. Preserve current SQLite pragmas, closing connection behavior, database path overrideability, schema versions, and tuple row behavior. The connection helper must obtain `SQL_DATABASE` when no path is supplied, open parent directories as needed, and expose a single initialization function that applies migrations transactionally.

### `utils/db/`

Keep compatibility imports for `connect_database`, `run_migrations`, and `LATEST_SCHEMA_VERSION`, delegating to the new canonical persistence package. Do not duplicate schema or connection implementations.

### `utils/sql_utils.py`

Use the canonical persistence connection and migration APIs. Remove `SQL_LOGGING_ENABLED` early-return guards from runtime/domain SQL helpers, including DB access, account mappings, watchlists, sell lists, split history, holdings, and generic database queries. Retain public helper signatures and return contracts. `init_db()` must always initialize schema and run the existing idempotent legacy JSON migration.

### `rsassistant/bot/core.py`

Initialize SQLite unconditionally at module startup and load SQL-backed watch/sell lists regardless of the legacy toggle.

### `utils/config_utils.py` and `config/.env.example`

Keep parsing the legacy environment key for compatibility, but document that it no longer disables operational SQLite persistence. Account mapping reads/writes and default nickname persistence must always use SQL. Report SQL persistence as active in `load_config()` while retaining the old environment key value for compatibility inspection.

### Tests

Add focused coverage proving DB initialization, DB connection, and account-mapping writes still work when `SQL_LOGGING_ENABLED` is false. Update config tests to verify the old switch no longer selects the JSON fallback or disables persistence. Preserve current migration and connection pragma tests.

## Non-goals

- Do not migrate order queue, sent-order log, split monitor, or holdings schemas in this packet.
- Do not redesign existing SQL tables or query semantics.
- Do not remove the legacy environment variable yet.
- Do not change tuple-based connection result behavior.

## Implementation order

1. Create canonical persistence connection/schema modules and compatibility re-exports.
2. Remove SQL logging gates from runtime/domain SQL helpers and config account mapping paths.
3. Make bot startup initialize SQL unconditionally and document the deprecated setting.
4. Add focused tests, then run compileall and full unittest discovery.
5. Move this packet to `completed/` and update `INDEX.md` and `TRACKER.md`.

## Acceptance criteria

- [ ] Runtime DB connection and schema migrations live under `rsassistant/persistence/`.
- [ ] Existing `utils.db` public imports remain compatible.
- [ ] Runtime SQL helpers and startup do not become disabled when `SQL_LOGGING_ENABLED=false`.
- [ ] Legacy account mapping reads/writes continue through SQL when the flag is false.
- [ ] Existing schema version and connection pragma behavior remain intact.
- [ ] Focused tests, full unittest discovery, and compileall pass.

## Completion report

Report the new canonical persistence API, compatibility surface, behavior of the legacy flag, and exact validation results.
