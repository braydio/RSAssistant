# TP-20261003-003: SQLite Runtime Foundation Completion

**Packet ID:** TP-20261003-003  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-003-sqlite-runtime-foundation.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-002  
**Priority:** High  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-002 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-002's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-002 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Finish and normalize the partially-landed SQLite foundation so runtime persistence has one connection/migration authority and is not disabled by the historical `SQL_LOGGING_ENABLED` toggle.

## Confirmed pre-dependency state

Current main already contains:

- `utils/db/connection.py`
  - `connect_database()`;
  - foreign keys ON;
  - busy timeout 5000;
  - 30-second SQLite timeout.
- `utils/db/migrations.py`
  - `PRAGMA user_version` migration runner;
  - current baseline tables;
  - migrations through current version;
  - WAL set by `run_migrations()`.
- `utils/db/__init__.py`.
- `utils/sql_utils.py` already imports `connect_database, run_migrations`.
- `rsassistant/bot/core.py` still wraps `init_db()` in:
  ```python
  if SQL_LOGGING_ENABLED:
      init_db()
      ...
  else:
      logger.info("SQL logging disabled; skipping database initialization.")
  ```
- `config/.env.example` still presents `SQL_LOGGING_ENABLED=true` as a persistence toggle.

## Architecture decision

Move the durable DB foundation under the target namespace now:

```text
rsassistant/persistence/
    __init__.py
    db.py
    migrations.py
```

Keep `utils/db/` temporarily as a compatibility shim re-exporting the new implementation so already-landed imports do not break.

Recommended shim:

```python
from rsassistant.persistence.db import connect_database
from rsassistant.persistence.migrations import LATEST_SCHEMA_VERSION, run_migrations

__all__ = ["connect_database", "run_migrations", "LATEST_SCHEMA_VERSION"]
```

Do not maintain two implementations.

## Required changes

### 1. `rsassistant/persistence/db.py` (new)

Move/centralize connection configuration.

Target:

```python
def connect_database(database):
    conn = sqlite3.connect(database, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
```

WAL may remain migration/startup-set rather than per-connection.

### 2. `rsassistant/persistence/migrations.py` (new)

Move current migration implementation unchanged first. Preserve current schema versions.

New migrations after this packet must append to this module, not recreate schemas ad hoc in feature modules.

### 3. `utils/db/*`

Convert to compatibility re-exports only.

### 4. `utils/sql_utils.py`

Import DB primitives from `rsassistant.persistence`, not implementation under `utils/db`.

Do not split domain SQL here yet.

### 5. `rsassistant/bot/core.py`

Runtime DB initialization must happen regardless of `SQL_LOGGING_ENABLED`.

Target startup pattern:

```python
init_db()
from utils.watch_utils import watch_list_manager
watch_list_manager.load_watch_list()
watch_list_manager.load_sell_list()
```

If some truly optional historical SQL logging remains, that feature may still consult `SQL_LOGGING_ENABLED`, but schema/runtime availability may not.

### 6. `utils/config_utils.py` and `config/.env.example`

Mark `SQL_LOGGING_ENABLED` deprecated.

Do not delete it yet because callers may still exist. Add a comment that it no longer controls runtime database availability and will be removed after persistence migration.

### 7. Tests

Add focused tests for:

- connection row factory;
- foreign keys enabled;
- busy timeout;
- migration idempotency;
- startup DB initialization with `SQL_LOGGING_ENABLED=false`;
- `utils.db` compatibility exports.

Suggested new test:

`unittests/db_runtime_test.py`

## Non-goals

- no order/split/holdings migration;
- no `sql_utils.py` decomposition;
- no config-toggle deletion;
- no schema redesign beyond preserving the current migration chain.

## Implementation order

1. dependency refresh;
2. move DB foundation under `rsassistant/persistence`;
3. add compatibility shim;
4. remove runtime DB gating in core;
5. deprecate config semantics;
6. tests.

## Acceptance criteria

- [ ] exactly one implementation of SQLite connection/migration primitives exists.
- [ ] `rsassistant/persistence/` owns it.
- [ ] `utils/db` is compatibility-only.
- [ ] runtime schema initializes even when `SQL_LOGGING_ENABLED=false`.
- [ ] existing schema version is preserved.
- [ ] migration runner remains idempotent.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report current schema version, compatibility shims retained, remaining `SQL_LOGGING_ENABLED` call sites, tests, and any assumptions that changed after Packet 002.