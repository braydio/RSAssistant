# TP-20261003-001: RSAssistant Persistence Modernization and Decomposition

**Packet ID:** TP-20261003-001  
**Status:** Ready  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-001-rsassistant-persistence-modernization.md`  
**Workstream size:** Controller packet for an 11-packet implementation train  
**Depends on:** None  
**Priority:** High  

## Objective

Finish the incomplete RSAssistant migration away from Excel/JSON/CSV as operational state stores, establish SQLite as the single mutable runtime/domain authority, and then decompose the largest utility/handler modules behind stable contracts.

This packet is the authoritative decomposition for the next modernization train. Do not run the legacy `docs/task-packets/rsassistant-hardening/00-09` sequence directly.

The expected implementation count is now **13 child packets**. The original 11 are TP-20261003-002 through TP-20261003-012, with two performance packets added after holdings-v2: TP-20261004-001 and TP-20261004-002.

TP-20261003-002 is Ready. All dependent children are intentionally Draft until their prerequisite implementation is reviewed and the next packet is refreshed.

Dependency review/refresh conversation:
https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

---

## Do not rediscover

The relevant current-main state has already been traced.

Confirmed files and behavior:

- `utils/sql_utils.py`
  - ~51 KB monolithic SQLite/data helper module.
  - owns Accounts, HistoricalHoldings, OrderHistory, HoldingsLive, account_mappings, watchlist, sell_list, ReverseSplitLog, ReverseSplitAccountEntries.
  - `init_db()` is gated by `SQL_LOGGING_ENABLED`.
  - `HoldingsLive.quantity` currently has `CHECK (quantity >= 0)`.
  - `update_holdings_live_batch()` skips negative quantities.
- `utils/order_queue_manager.py`
  - `volumes/db/order_queue.json` is still the authoritative runtime store.
- `utils/order_send_log_manager.py`
  - `volumes/db/order_send_log.json` is still authoritative.
- `utils/split_watch_utils.py`
  - module-level `data` plus `volumes/db/split_watchlist.json` is still authoritative.
- `utils/csv_utils.py`
  - holdings ingestion writes SQL through `update_holdings_live_batch()`;
  - holdings operational reads still use `HOLDINGS_LOG_CSV`;
  - `sell_all_position()` reads CSV directly;
  - `get_top_holdings()` reads CSV directly;
  - order CSV is still a compatibility/runtime path.
- `utils/holdings_snapshot.py`
  - reads `HOLDINGS_LOG_CSV`.
- `utils/audit_watchlist_utils.py`
  - reads `HOLDINGS_LOG_CSV`.
- `utils/holdings_importer.py`
  - JSON snapshot input ultimately routes through `save_holdings_to_csv()`.
- `utils/excel_utils.py`
  - Excel is hard-disabled/deprecated, but the module still ships.
- `requirements.txt`
  - still includes `openpyxl`.
- `config/.env.example`
  - still includes `EXCEL_LOGGING_ENABLED`.
- `docker-compose.yml`
  - still mounts `./volumes/excel:/app/volumes/excel`.
- `entrypoint.sh`
  - still creates `$VOLUMES_DIR/excel`.
- `.github/workflows/submit-pr.yaml`
  - is not CI; it is a stale/broken auto-PR workflow.
- There is currently no `utils/runtime_db.py`.
- The legacy hardening Packet 06 and Packet 07 contain useful SQLite target ideas but were never implemented on current main.

Do not perform a repo-wide architecture audit before starting the child train. Verify only each child packet's named seams.

---

# Architecture lock

The destination architecture is:

```text
rsassistant/bot/          Discord I/O, cogs, handlers, scheduling
rsassistant/services/     application/domain orchestration
rsassistant/persistence/  SQLite connection, migrations, repositories
utils/                    generic/pure helpers only

SQLite                    authoritative mutable runtime/domain state
CSV                       import/export/audit/operator-readable output only
JSON                      legacy migration input only
Excel                     historical artifact only
config/ + environment     operator configuration only
```

Rules:

1. One authoritative mutable state store per domain.
2. SQLite under `VOLUMES_DIR/db/` owns runtime/domain state after migration.
3. CSV must not remain a second operational read/write database after a domain migrates.
4. JSON runtime files are migration inputs only after their domains move to SQL.
5. Excel must not regain runtime authority.
6. Public helper APIs should remain stable during storage migration whenever practical.
7. Split modules behind stable APIs after persistence authority is settled, not before.
8. Avoid a big-bang rewrite of `utils/sql_utils.py` or `on_message.py`.

---

# Expected child packet train

## Packet 1 of 13: CI baseline

### Purpose

Create a trustworthy test gate before persistence changes.

### Expected files

- `.github/workflows/ci.yml` (new)
- `.github/workflows/submit-pr.yaml`
- optionally `requirements-dev.txt`
- `AGENTS.md` only if command documentation needs correction

### Recommended implementation

Use the project's existing unittest suite rather than first converting frameworks.

CI should run at minimum:

```bash
python -m compileall .
python -m unittest discover -s unittests -p '*_test.py'
```

Delete `.github/workflows/submit-pr.yaml` if it remains the current broken workflow that creates one branch name and pushes another.

Do not convert the suite to pytest in this packet.

### Exit gate

A normal push/PR to main executes compile + unit tests.

---

## Packet 2 of 13: SQLite runtime foundation

### Purpose

Create one runtime DB connection/migration layer and stop treating SQL as optional logging.

### Expected files

- `rsassistant/persistence/__init__.py` (new)
- `rsassistant/persistence/db.py` (new)
- `rsassistant/persistence/schema.py` or `migrations.py` (new)
- `utils/sql_utils.py`
- `rsassistant/bot/core.py`
- `utils/config_utils.py`
- `config/.env.example`
- new focused tests

### Recommended connection helper

```python
def connect_runtime_db() -> sqlite3.Connection:
    conn = sqlite3.connect(SQL_DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn
```

Use a schema version mechanism, preferably a small `schema_migrations` table or `PRAGMA user_version`.

Operational persistence must not disappear when `SQL_LOGGING_ENABLED=false`.

Recommended compatibility strategy:

- retain the config key temporarily;
- stop using it to gate runtime DB initialization;
- if retained, redefine it narrowly as optional historical/event SQL logging only;
- migrate call sites before deleting the setting in a later cleanup packet.

Do not rewrite all SQL helpers here.

---

## Packet 3 of 13: Order runtime JSON -> SQLite

### Purpose

Replace whole-file runtime mutation in:

- `utils/order_queue_manager.py`
- `utils/order_send_log_manager.py`

### Expected tables

```sql
CREATE TABLE scheduled_orders (
    order_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    broker TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_scheduled_orders_scheduled_at
ON scheduled_orders(scheduled_at);

CREATE TABLE rsa_order_send_log (
    send_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    command TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity REAL NOT NULL,
    broker TEXT NOT NULL
);

CREATE INDEX idx_rsa_order_send_log_sent_at
ON rsa_order_send_log(sent_at);
```

Preserve existing public helper signatures.

Legacy migration inputs:

- `volumes/db/order_queue.json`
- `volumes/db/order_send_log.json`

Migration must be transactional, idempotent, and rename the source to `*.migrated` only after successful commit.

Reuse the good parts of historical Packet 06, but rebase against current main.

---

## Packet 4 of 13: Split monitor JSON -> SQLite

### Purpose

Remove module-global JSON-backed split-monitor state.

### Expected files

- `utils/split_watch_utils.py`
- `rsassistant/bot/cogs/split_monitor.py`
- persistence repository module
- focused tests

### Recommended tables

```sql
CREATE TABLE split_monitor (
    ticker TEXT PRIMARY KEY,
    split_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('buying', 'selling')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE split_monitor_accounts (
    ticker TEXT NOT NULL,
    account_name TEXT NOT NULL,
    bought INTEGER NOT NULL DEFAULT 0,
    sold INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ticker, account_name),
    FOREIGN KEY (ticker) REFERENCES split_monitor(ticker) ON DELETE CASCADE
);
```

Preserve:

- `add_split_watch`
- `mark_account_bought`
- `update_split_status`
- `mark_account_sold`
- `cleanup_completed_tickers`
- `get_watchlist`
- `get_status`
- `get_full_watchlist`
- `remove_split_watch`
- `get_all_accounts`

Legacy input:

- `volumes/db/split_watchlist.json`

Reuse historical Packet 07 only as a design reference.

---

## Packet 5 of 13: Holdings SQL contract v2

### Purpose

Make SQL capable of representing the full current holdings domain before any reader migration.

This packet is required because current `HoldingsLive` is not semantically equivalent to CSV:

- it rejects negative quantity;
- `update_holdings_live_batch()` skips negative positions;
- it is append-oriented rather than an atomic current snapshot;
- current CSV rows include broker/group/account identity plus account total/timestamps.

Do not simply point readers at current `HoldingsLive`.

### Recommended schema direction

Prefer a canonical current-position table keyed by account + ticker:

```sql
CREATE TABLE holdings_current (
    account_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    position_value REAL NOT NULL,
    account_total REAL,
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (account_id, ticker),
    FOREIGN KEY (account_id) REFERENCES Accounts(account_id)
);
```

Negative quantity must be valid.

Use atomic refresh semantics. Recommended approaches:

A. staging table + transaction:

```text
begin refresh
  -> write holdings_refresh_staging
  -> validate complete snapshot
  -> BEGIN IMMEDIATE
  -> replace holdings_current for affected scope
  -> COMMIT
```

or B. refresh generation IDs with one active generation.

Pick one and test crash/partial refresh behavior.

Keep `HistoricalHoldings` separate from the current snapshot contract.

### Expected files

- persistence holdings repository (new)
- schema/migration layer
- `utils/sql_utils.py` compatibility delegates
- `utils/csv_utils.py` ingestion seam
- holdings-focused tests

Do not migrate production readers in this packet.

---

## Added Packet: Performance History Capture

Canonical child: `TP-20261004-001`

Runs after Holdings SQL Contract v2 and before holdings authority inversion.

Purpose:

- persist one account-value observation per successful holdings refresh;
- preserve reported account totals separately from summed position values;
- backfill historical position-value data from `HistoricalHoldings`;
- preserve valuation basis so older positions-only history is not confused with newer account-total history;
- create the durable time series required for recent growth and historical visibility.

---

## Packet 6 of 13: Holdings authority inversion

### Purpose

Make SQL the operational holdings read source.

### Expected readers to migrate

- `utils/holdings_snapshot.py`
- `utils/audit_watchlist_utils.py`
- `utils/csv_utils.get_top_holdings()`
- `utils/csv_utils.sell_all_position()`
- holdings-related cogs/helpers
- any timestamp/freshness checks using `HOLDINGS_LOG_CSV`

Create repository queries that return domain dictionaries matching callers so the UI/cogs do not need storage knowledge.

CSV becomes generated compatibility output only.

Recommended writer flow:

```text
incoming snapshot
 -> normalize/validate
 -> transactional SQLite current snapshot
 -> optional CSV export from committed SQL state
```

Never use:

```text
incoming snapshot
 -> write CSV
 -> reread CSV
 -> derive operational state
```

After this packet, disabling CSV export must not break holdings commands.

---

## Added Packet: Performance Visibility and Growth History

Canonical child: `TP-20261004-002`

Runs after holdings authority inversion + performance history capture.

Purpose:

- add `..performance` / `..perf` / `..growth`;
- show current value plus 1D/7D/30D/90D/YTD/1Y/all-time value change;
- show dollar and percentage growth;
- render historical value charts;
- support account/broker filtering;
- protect comparisons against changing account coverage;
- clearly label value growth rather than true cash-flow-adjusted investment return.

---

## Packet 7 of 13: OrderHistory authority + CSV demotion

### Purpose

Make `OrderHistory` the canonical order-history source and demote `orders_log.csv` to export/audit compatibility.

### Expected files

- `utils/csv_utils.py`
- `utils/sql_utils.py` / new order repository
- `rsassistant/bot/cogs/orders.py`
- `rsassistant/bot/cogs/split_monitor.py`
- reporting/order readers
- tests

Inventory every `ORDERS_LOG_CSV` reader before changing authority.

After migration, operational queries must read SQL. CSV can be regenerated/exported.

---

## Packet 8 of 13: Excel retirement

### Preconditions

Packets 2-7 complete and no live call site relies on Excel.

### Expected removal

- `utils/excel_utils.py`
- `unittests/excel_utils_test.py`
- `openpyxl` from `requirements.txt`
- `EXCEL_LOGGING_ENABLED`
- `EXCEL_FILE_MAIN` and dead Excel config
- Docker `volumes/excel` mount
- Excel directory creation in `entrypoint.sh`
- stale runtime docs/help

Keep `docs/excel_to_sql_mapping.md` as historical migration documentation, but mark the migration complete and remove wording that implies live Excel code remains.

---

## Packet 9 of 13: Decompose sql_utils.py by domain

### Purpose

Shrink the 51 KB persistence monolith only after storage contracts are stable.

### Target modules

```text
rsassistant/persistence/accounts.py
rsassistant/persistence/watchlists.py
rsassistant/persistence/orders.py
rsassistant/persistence/holdings.py
rsassistant/persistence/reverse_splits.py
```

Use a strangler pattern:

1. move implementation by domain;
2. keep `utils/sql_utils.py` as temporary compatibility imports/wrappers;
3. migrate callers;
4. assert no circular dependencies;
5. delete compatibility wrappers only when search proves no production imports remain.

Do not rewrite queries just for style while moving them.

---

## Packet 10 of 13: Decompose on_message.py into services

### Purpose

Reduce the ~44 KB Discord handler without mixing persistence changes into the same packet.

### Boundary

Keep Discord event objects, sends, reactions, and channel resolution in `rsassistant/bot/`.

Extract application orchestration into `rsassistant/services/`, likely:

```text
alert_processing.py
order_orchestration.py
holdings_refresh.py
policy_orchestration.py
```

Service functions should accept plain values/domain objects rather than Discord contexts whenever practical.

Preserve behavior and tests.

---

## Packet 11 of 13: Parsing/runtime cleanup

### Purpose

Finish the migration with bounded cleanup after authority and module boundaries are stable.

Expected work:

- split `utils/parsing_utils.py` along real parser domains;
- move blocking work off the Discord event loop where still present;
- add heartbeat freshness healthcheck;
- prune dependencies proven unused by search/tests;
- reconcile architecture docs;
- remove compatibility toggles/files whose migrations are complete;
- inspect `externalization-staging/` and either document or remove it;
- finish plugin-entrypoint mismatch only if still present.

Do not introduce a new persistence architecture in this final packet.

---

# Dependency order

```text
1 CI baseline
  ↓
2 SQLite foundation
  ↓
3 order runtime persistence ─┐
4 split monitor persistence ├─ may run separately after 2
5 holdings SQL v2 ──────────┘
  ↓
Performance history capture (TP-20261004-001)
  ↓
6 holdings authority inversion
  ↓
Performance visibility (TP-20261004-002)
  ↓
7 order-history authority
  ↓
8 Excel retirement
  ↓
9 sql_utils decomposition
  ↓
10 on_message decomposition
  ↓
11 parsing/runtime cleanup
```

Packets 3, 4, and 5 may be implemented independently after Packet 2 if branch/workstream locking permits. Packet 6 requires 5. Packet 8 requires the persistence-authority work to be complete.

---

# Packet creation protocol

This controller packet does not authorize a child agent to improvise all 11 changes in one run.

All children are now authored. Before implementing each Draft child:

1. finish and review its dependency;
2. re-open current main;
3. use the packet's dependency-refresh checkpoint and the review conversation above;
4. update assumptions/code recommendations if the dependency changed the seam;
5. change the child from Draft to Ready in both packet and tracker;
6. implement only that child packet.

Do not skip the refresh checkpoint merely because the pre-authored packet still appears plausible.

---

# Global acceptance criteria

The modernization train is complete only when:

- [ ] normal PRs/pushes have a real compile + unit-test CI gate;
- [ ] runtime SQLite initialization is not disabled by a historical logging toggle;
- [ ] order queue runtime state is not JSON-authoritative;
- [ ] sent-order audit runtime state is not JSON-authoritative;
- [ ] split monitor runtime state is not module-global/JSON-authoritative;
- [ ] SQL represents negative holdings and atomic current snapshots correctly;
- [ ] holdings operational readers use SQL;
- [ ] account/portfolio value snapshots are retained historically;
- [ ] operator can see recent value growth and historical trends with coverage/basis disclosure;
- [ ] CSV holdings output can be disabled without breaking operational holdings behavior;
- [ ] OrderHistory is authoritative for order-history reads;
- [ ] Excel runtime code/dependency/config/volume is removed;
- [ ] `utils/sql_utils.py` is decomposed behind stable domain repository modules;
- [ ] Discord orchestration is thinner and domain services do not require Discord contexts unnecessarily;
- [ ] no new JSON/CSV/Excel operational database is introduced;
- [ ] full unittest suite and compileall pass after each child packet.

---

# Standard validation

Focused child validation belongs in each child packet.

Every child should end with:

```bash
python -m compileall .
python -m unittest discover -s unittests -p '*_test.py'
```

After Packet 1 lands, CI must run equivalent commands automatically.

---

# Completion report for this controller

When the entire train is complete, report:

1. child Packet IDs and final statuses;
2. authoritative state store for each domain;
3. legacy files retired/migrated;
4. final persistence module map;
5. remaining compatibility shims, if any;
6. test/CI status;
7. intentional deviations from this decomposition.

## Design lock summary

Do not attack the giant modules first. Lock one SQLite authority per domain, migrate runtime state behind stable APIs, retire Excel/JSON/CSV authority, then decompose the code around those stable seams.
