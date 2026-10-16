# RSAssistant + auto-rsa: pre-migration audit (local state)

Audited: 2026-10-15, read-only. No code, config, container or DB was modified by this audit.
Method: git, `docker inspect`/`docker logs`, read-only SQLite (`mode=ro`), `grep`, file listings.
Secrets: `.env` contents, credentials, tokens and account numbers were deliberately not read or recorded. Only key names, counts and aggregates appear below.

This report answers the "What I need from your local installation" section of the proposed architecture and corrects or confirms its GitHub-only claims.

---

## 0. Headline findings (read these first)

1. **The live RSAssistant container is running the latest `main` (HEAD `001e425`), and production DB is already at schema v10.** Both containers were recreated at 2026-10-15 23:43 ET, after the TP-20261013-001/002 commits. `split_events.py` is present in the running container, and `PRAGMA user_version` on `volumes/db/rsa_database.db` is `10`. So the new split-intent tables exist in production (both empty) and the new fail-closed error watcher code is live. *Update: TP-20261013-001 is therefore not "to be completed" before migration (it is done, committed, deployed).* I did not trigger that restart; it appears to have been done by something else on this host.
2. **There is no single "production branch".** Deployment is `docker compose up --build` from the working tree of `~/Production/RSAssistant` (`main`). `origin/production` is a dead branch (last commit 2025-05-01, 516 commits behind `main`, ~29k lines different). Provenance of what runs = the local checkout state at build time, with the `.git` directory copied into the image (`.dockerignore` keeps `.git` because of runtime self-update).
3. **auto-rsa is a nested, gitignored git repo, not a submodule.** `RSAssistant/auto-rsa/` is `braydio/auto-rsa` (`main` = `origin/main` = `110439c`, clean, 0 behind; against a freshly fetched `upstream/main` it is **2 ahead / 0 behind**, matching the proposal. The local upstream ref was stale and showed 51 ahead before fetching). It is excluded by `.gitignore`, so the RSAssistant repo history does not pin the version of auto-rsa that runs. Docker builds the auto-rsa image from this directory and then **bind-mounts `./auto-rsa/src` read-only over `/app/src`**, so the live code is whatever is on disk in `auto-rsa/src`, regardless of what was baked into the image.
4. **The two apps are coupled through three channels, not one:** (a) Discord text commands (`!rsa buy|sell|holdings ...`) sent by the RSAssistant bot into the same channel the auto-rsa bot listens on; (b) a **JSON holdings snapshot file** written by a patch in the auto-rsa fork (`AUTO_RSA_HOLDINGS_FILE`) on the shared `volumes/db` bind mount and imported by RSAssistant; (c) the **shared `volumes/db` directory** itself (auto-rsa mounts it rw). The ULT-MA plugin additionally expects an **HTTP API on auto-rsa** (`plugins/ultma/executor.py`), which the fork does not appear to provide (unverified, see §9).
5. **Order-result capture appears to have silently stopped.** `rsa_order_send_log` (orders RSAssistant *sent*) has 209 rows through 2026-10-15, including 151 since 2026-08-05 (120 in Sept). `OrderHistory` (orders *confirmed*) has **zero rows after 2026-07-30** (33 rows in July, none Aug–Oct). Either confirmation parsing/ingest stopped working, SQL logging is off in the live config, or nothing in that window produced a parseable confirmation. Not diagnosed. This matters because the proposed design depends on reconciling sends against fills, and the legacy "fill" evidence is currently absent for ~11 weeks.
6. **Three more copies of auto-rsa-ish code exist on disk** and must be inventoried before anything is called canonical (§4).
7. **Test baseline:** 214 unittest pass; pytest: 296 pass, 6 fail. The same 6 fail on clean `HEAD`, from before this work (stale `RSAssistant` module-attribute patches in `all_command`, `brokerwith`, `order_remove` x2, `sell_queue` x2). CI (`.github/workflows/ci.yml`) runs only `compileall` + `unittest discover` on Python 3.12 (local venv is 3.14, auto-rsa container is 3.14.3, RSAssistant Dockerfile targets 3.12).

---

## 1. What is deployed right now

| Item | Value |
|---|---|
| Orchestrator | `docker compose` project `rsassistant`, file `RSAssistant/docker-compose.yml`, working dir `~/Production/RSAssistant` |
| Services running | `RSAssistant` (image `rsassistant-rsassistant`, healthy), `auto-rsa` (image `auto-rsa-holdings:local`, no healthcheck) |
| Not running | `watchtower` (profile `upstream-image-updates`, opt-in) and both systemd units (`rsassistant.service`, `autorsa-gui.service`: `inactive`) |
| Image provenance | Both built locally ("classic" builder); no registry, no tags beyond `latest`/`local`; no pinned digests |
| Restart policy | `unless-stopped` for both |
| Limits | RSAssistant: 512M / 1 CPU. auto-rsa: none |
| Shared state | `./volumes/db` is mounted rw in **both** containers |
| Other containers on host (unrelated) | mediacycler-shelf, EmailMonitor, glance, Dashy, weatherboy, chromadb |

### RSAssistant container
- `WORKDIR /app`, entrypoint `/app/entrypoint.sh` → `python /app/RSAssistant.py`. Python 3.12-slim, `git` installed (self-update).
- Config: `env_file: ./config/.env` (injected as env vars) **and** `./config` mounted at `/app/config`; `utils/config_utils.py` also calls `dotenv.load_dotenv` (honours `ENV_FILE`, else default path). Two config channels for the same file.
- Mounts: `config`, `volumes/{logs,db,cache}`. Healthcheck `scripts/healthcheck.py` (heartbeat file age < 180s).
- Note: `volumes/logs/app.log` and several other files in `volumes/` are **root-owned** (written by the container), which breaks local test runs unless `VOLUMES_DIR` is redirected.

### auto-rsa container
- `WORKDIR /app`, entrypoint starts `Xvfb :99` then `exec auto_rsa_bot docker` (Discord bot mode). Python 3.14.3. RSA Version `2.2.0`.
- Config: `env_file: ./auto-rsa/.env` (container reports "Directory Contains .env File: False": it relies purely on injected env). Editing `.env` requires `docker compose up -d auto-rsa` (recreate), not `restart`.
- Mounts: `auto-rsa/creds → /app/creds` (rw), `auto-rsa/src → /app/src` (ro), `volumes/db → /app/volumes/db` (rw).
- Credentials in `auto-rsa/creds/` (names only): `chase_1`, `Fidelity_Fidelity 1/2.json`, `robinhoodRobinhood 1.json/.pickle`, `Vanguard_Vanguard_1.json`, `ZenFidelity_1/2`.
- The container just (re)connected to Discord at 23:43; no errors in the last log lines.

### Discord topology
RSAssistant bot ("Order Flowbot") and the auto-rsa bot are separate Discord bot users in the same server. Channel IDs (primary/secondary/tertiary/holdings) are configured via env. RSAssistant posts `!rsa ...` commands into the primary channel; the auto-rsa bot executes them and posts embeds; RSAssistant's `on_message` handler parses those replies (e.g. `"!rsa holdings" in lowered_content` at `rsassistant/bot/handlers/on_message.py`).

---

## 2. Repositories and code state

| Path | Remote | Branch / HEAD | Working tree | Role |
|---|---|---|---|---|
| `~/Production/RSAssistant` | `braydio/RSAssistant` | `main` @ `001e425`, == `origin/main` after my 2 local commits (**not pushed**) | 1 pre-existing deletion (`RSDashboard.local.trash-20261010`) | canonical app, 564 commits |
| `RSAssistant/auto-rsa` | `braydio/auto-rsa` (+`upstream` = NelsonDane/auto-rsa) | `main` @ `110439c` | clean | **what the container runs** (src is bind-mounted) |
| `RSAssistant/AutoRSA-GUI.local` | `braydio/AutoRSA-GUI-Arch` | `main` @ `ca03e68` | **dirty**: modified `chaseAPI.py`, `fennelAPI.py`, `wellsfargoAPI.py` (424 insertions, 94 deletions), plus many untracked chase error dumps, nested `NelsonDane-fennel-invest/`, `NelsonDane-fidelity-api/`, `Arch/`; 3.1 GB | older monolithic GUI/CLI fork (see §4) |
| `RSAssistant/auto-rsa.local` | (plain dir, no `.git` of its own; git resolves to the parent repo) | n/a | 1.1 GB | older Oct-3 snapshot of auto-rsa with `docker-compose.override.yml`, `gui.py`, `override.env`, `fennel_api.local` |
| `~/Production/auto-rsa` | `braydio/auto-rsa` | `main` == `origin/main` | untracked `NelsonDane-fennel-invest/`, `NelsonDane-fidelity-api/` | **second clone** of the fork; differs from the container's copy in Dockerfile, compose, entrypoint, workflows, `.env`, docs (not diffed in detail) |
| `~/Production/AutoRSA-GUI` | (git) | `main` == `origin/main` | untracked `autorsa_web/requirements.txt`, error dumps | web GUI variant (`autorsa_web/`); `.local` sibling above is the Arch fork |

### auto-rsa fork vs upstream
- 2 commits ahead of upstream, 0 behind. Local `upstream/main` ref was stale until fetched (51 ahead against the stale ref).
- The fork's own big commit `110439c` (Oct 10, a single squash "of months of uncommitted working-tree edits; no incremental history existed on disk") contains: Fidelity rewrite (`src/brokerages/fidelity_api.py` +1834/-… now 1707 lines, Zendriver-based), Wells Fargo fixes (603 lines), `helper_api.py` holdings-snapshot export, Docker/entrypoint tweaks, 495 + 58 lines of unit tests for Fidelity and WF, and a `uv.lock` rewrite (3.4k lines).
- Submodules (`.gitmodules`): `styles`, `src/vendors/robin_stocks` (ImNotOssy `multi` branch), `src/vendors/webull` (NelsonDane `dev` branch). Both vendors are third-party forks pinned by commit. Their presence inflates the tree (`src` has ~19.5k Python lines, most of it vendor code).
- Broker adapters present in the fork (`src/brokerages/`): bbae, chase, dspac, fennel, fidelity, firstrade, public, robinhood, schwab, sofi, tasty, tornado, tradier, vanguard, webull, wellsfargo (16). Largest: fidelity 1707, sofi 821, wellsfargo 603, tornado 545, dspac 318, chase 316, bbae 314.
- The coupling shim is in `src/helper_api.py::print_all_holdings`: it builds `snapshot_entries` (`broker, group, account, ticker, quantity, price, value, account_total`) and merges them, **by broker**, into the JSON file named by `AUTO_RSA_HOLDINGS_FILE`, replacing the prior entries for that broker. RSAssistant also ships `scripts/apply-auto-rsa-patch.sh` + `patches/auto-rsa-holdings.patch` and an admin command `..patchautorsa` that applies this same patch to an auto-rsa checkout (now redundant for the fork, which has it committed).
- Licensing: auto-rsa is GPLv3 (`LICENSE` 35 KB in the fork); RSAssistant is MIT. Vendored `robin_stocks` / `webull` carry their own licences (not reviewed).

---

## 3. RSAssistant structure (current `main`)

| Area | Files / lines |
|---|---|
| `rsassistant/` (bot, cogs, handlers, persistence, services) | 37 files, ~7.6k lines |
| `utils/` | 32 files, ~9.0k lines |
| `plugins/ultma/` | 12 files, ~1.8k lines (own cog, state, executor, market data, tests) |
| `scripts/` | 5 files, ~0.9k lines |
| `unittests/` | 56 files, ~6.0k lines |

Largest modules: `rsassistant/bot/handlers/on_message.py` 1237, `utils/parsing_utils.py` 1217, `utils/csv_utils.py` 871, `utils/utility_utils.py` 840, `utils/config_utils.py` 824, `utils/policy_resolver.py` 804, `utils/watch_utils.py` 667, `rsassistant/persistence/schema.py` 474.

### Commands (prefix `..`, aliases exist)
Roughly 39 registered command names across 10 cogs (the proposal counted 36 before my 4 new `split*`/`watcherstatus` commands): `addmap addratio aliases all brokerlist brokerwith clear clearholdings clearmap grouplist history lastorder liquidate loadlog loadmap order orders ownersummary patchautorsa performance queue queue_run remove shutdown snapshot splitcleanup splitlist splitorders splitreplace splitresolve splitreview splitstatus splitwatch top watch watched watcherstatus watchlist xsplits` (+`restart` via admin, ULT-MA commands registered in `plugins/ultma/cog.py` by a different mechanism and not counted). Per cog: accounts 5, admin 3, aliases 1, holdings 4, orders 8, performance 1, error-watcher 1, reporting 4, split_monitor 8, watchlist 4.

### Scheduling / background
APScheduler jobs registered in `rsassistant/bot/tasks.py` (3-4 `add_job` calls incl. a conditional holdings job when `AUTO_RSA_HOLDINGS_ENABLED`), plus `run_total_refresh_scheduler` and `reschedule_queued_orders`. Order timing runs through `utils/order_dispatcher.py` (single asyncio dispatcher, TP-20261010-011). Market-hours logic in `utils/market_calendar.py` with `config/market_holidays.txt`.

### Runtime self-modification
`utils/update_utils.py` (54 lines) does git pull/revert + restart; imported only by `on_message.py` (`update_and_restart`, `revert_and_restart`), triggered by a trusted auto-rsa bot ID (`TRUSTED_AUTORSA_BOT_ID`) via `..updatebot` / `..revertupdate`. This is why the image keeps `.git`.

### Configuration
`config/.env.example` has 74 keys; live config is `config/.env`; also `config/settings.yml`, `account_mapping.json`, `watch_list.json`, `sell_list.json`, `autobuy_overrides.json`, `ignore_brokers.txt`, `ignore_tickers.txt`, `overdollar_actions.json`, `tagged_alerts.txt`, `temp.env` (purpose unknown). Several of these JSON/TXT files are still runtime inputs (not all migrated to SQLite). Live flag state (non-secret): `AUTO_RSA_HOLDINGS_ENABLED=true`, `AUTO_SELL_LIVE=false`; `SQL_LOGGING_ENABLED`, `CSV_LOGGING_ENABLED`, `ENABLED_PLUGINS`, `AUTO_BUY_WATCHLIST` and `AUTO_RSA_ERROR_WATCHER_ENABLED` are **not set** in the live `.env` (defaults apply; see §9 for the SQL logging question).

---

## 4. Duplicated/legacy copies of the broker code (to resolve before declaring a baseline)

Five locations hold overlapping broker code. Only #1 is proven to be live.

1. `RSAssistant/auto-rsa` @ `110439c` (modern `src/brokerages/*_api.py` layout, uv/pyproject, Zendriver Fidelity). **Live.**
2. `~/Production/auto-rsa` @ same commit, but with different Dockerfile/compose/entrypoint/workflows/.env: an alternative deployment config for the same code.
3. `RSAssistant/auto-rsa.local`: Oct-3 snapshot with local override files; no git history of its own.
4. `RSAssistant/AutoRSA-GUI.local` (Arch fork, `*API.py` flat layout, bbae/chase/dspac/fennel/… ) with **uncommitted Chase/Fennel/Wells Fargo changes**, and `~/Production/AutoRSA-GUI` (clean, web-GUI variant, `autorsa_web/`).
5. Nested third-party checkouts: `NelsonDane-fidelity-api/` and `NelsonDane-fennel-invest/` appear untracked in three places (`auto-rsa`, `~/Production/auto-rsa`, `AutoRSA-GUI.local`), plus `RSAssistant/auto-rsa.local/fennel_api.local`.

**Risk:** the GUI forks hold the only copy of any Chase/Fennel/Wells Fargo fixes not yet in the modern fork's `src/brokerages`. The modern fork's Chase and Fennel adapters (316 and unknown lines) have no tests; only Fidelity and Wells Fargo have tests (`unittests/fidelity_api_test.py`, `wellsfargo_api_test.py`). No diff of Chase/Fennel between the GUI fork and the container fork was performed here. `autorsa-gui.service` (systemd, `inactive`) points at `AutoRSA-GUI.local` and is a third potential bot process using the same Discord identity.

---

## 5. Data: what the production SQLite DB actually contains

`volumes/db/rsa_database.db`, `user_version = 10`, WAL. Also on the same mount: `auto_rsa_holdings.json` (85 KB, updated 23:10 today), `fidelity_errors/`, `*.json.migrated` markers for order queue, send log and split watchlist, and a `rsa_database.db.bak-20261010-pre-backfill` manual backup.

| Table | Rows | Notes |
|---|---|---|
| `Accounts` | 225 | `account_id, broker, account_number, account_nickname, broker_number` |
| `account_mappings` | 202 | legacy mapping store, still present next to `Accounts` |
| `HistoricalHoldings` | 43,132 | |
| `HoldingsLive` | 81,818 | positive-only append feed (`holding_id, account_id, ticker, quantity, average_price, timestamp`) |
| `holdings_current` | 1 | current-snapshot contract table (TP-006/007); only 1 row, odd (see §9) |
| `holdings_refreshes` / `holdings_refresh_staging` | 0 / 0 | |
| `account_value_snapshots` | 3,714 | latest 2026-10-12 17:44 |
| `OrderHistory` | 1,198 | **latest 2026-07-30**: 2025-05: 841, 2025-06: 322, 2025-08: 2, **2026-07: 33, then nothing** |
| `rsa_order_send_log` | 209 | 2026-05-14 → 2026-10-15; 107 buy / 102 sell; 2026-09 alone: 120 |
| `scheduled_orders` | 0 | queue empty |
| `sell_list` | 144 | |
| `watchlist` | 6 | |
| `split_monitor` / `split_monitor_accounts` | 4 / 17 | open watches: BTOC (2026-10-15), KNDI (2026-10-16), FRGT (2026-10-19), OBAI (2026-10-19), all `buying` |
| `split_event_intents` / `split_event_order_intents` | 0 / 0 | new in v10 (applied by today's rebuild). The four watches above pre-date intent tracking; a replayed alert for them resolves as `already_claimed` (recorded `submitted`, reason `preexisting_watch`) with no new buy. |
| `ReverseSplitLog` / `ReverseSplitAccountEntries` | 0 / 0 | historical reverse-split log is empty |
| `legacy_imports` | 1 | ledger for one-time imports |

OrderHistory brokers (all-time counts): Fennel 297, Robinhood 261, Fidelity 223, Webull 130, Wellsfargo 118, BBAE 99, DSPAC 64, Schwab 6.
Current holdings snapshot (557 position rows): Robinhood 185, Fidelity 126, Public 114, Fennel 110, WELLSFARGO 17, VANGUARD 5.

**Active-broker picture** (union of the above, for adapter prioritisation): Fidelity (largest custom work; 2 logins + "Zen" variants), Robinhood, Fennel, Public, Wells Fargo, Vanguard, Webull, BBAE, DSPAC appear in recent data; Chase credentials exist; Schwab minimal; Tradier/Tasty/Tornado/Firstrade/SoFi have adapters but no evidence of recent use in this DB. This needs the owner to confirm.

Schema authority: `rsassistant/persistence/schema.py` (`LATEST_SCHEMA_VERSION = 10`, 10 sequential `PRAGMA user_version` migrations, each transactional). `utils/sql_utils.py` (196 lines) is only a compatibility facade.

Other mutable state **outside SQLite** still in use: `config/watch_list.json`, `config/sell_list.json`, `config/account_mapping.json`, JSON alert-dedup state in `utils/monitor_utils.py`, ULT-MA state (`plugins/ultma/state.py`), `volumes/cache` (price cache), `volumes/db/auto_rsa_holdings.json`, auto-rsa's own `creds/*.json|pickle` and per-broker state.

---

## 6. Task-packet and process state

- All executable packets except TP-20261003-001 (umbrella, *In Progress*) and TP-20261003-012 (*Draft, refresh-required*) are Complete: TP-20261003-002…011, TP-20261004-001/002/008, TP-20261010-001…011, **TP-20261013-001 (split lifecycle + autobuy idempotency)** and **TP-20261013-002 (read-only Codex error watcher)** (both completed today).
- Packet governance: `AGENTS.md` + `docs/task-packets/{README,INDEX,TRACKER}.md`, lifecycle folders, durable summaries in `docs/task-packets/summaries/`. The migration should be authored as new canonical packets in this system (IDs `TP-YYYYMMDD-NNN`); the old `rsassistant-hardening/` train is superseded and not executable.
- "Persistence modernization rule" in `AGENTS.md` (SQLite owns mutable state; CSV/JSON only as import/export) already aligns with the proposed single-database direction.

What TP-20261013-001 changed that the migration must preserve: durable `(ticker, split_date)` event identity (`split_event_intents`, `split_event_order_intents`, unique `order_id`), atomic `claim_split_event` (`claimed | already_claimed | invalid | requires_review`), fail-closed date validation (no "today" default; window −14 / +400 days), per-plan stable dispatch keys, `needs_reconciliation` instead of auto-retry, completion predicate `bought ⊆ sold` and not blocked by reconciliation, and new operator commands `splitreview`, `splitresolve`, `splitreplace`. `split_monitor` is still keyed by ticker only (deliberately not re-keyed).

---

## 7. Verification of the "dead code" claims

Static caller search (non-test `.py` under `rsassistant`, `utils`, `plugins`, `scripts`, `RSAssistant.py`; and tests). **Static only: no runtime trace, no coverage run, no check for dynamic/`importlib` loading.** No vulture/coverage is installed in the venv.

| Module | Lines | Non-test importers | Test importers | Verdict |
|---|---|---|---|---|
| `utils/reverse_split_parser.py` | 31 | 0 | 0 | **No callers anywhere**: delete candidate (confirmed statically) |
| `utils/autobuy_utils.py` | 48 | 0 | 0 | **No callers anywhere**: delete candidate (confirmed statically) |
| `utils/audit_watchlist_utils.py` | 53 | 0 | 0 | **No callers anywhere**: delete candidate (confirmed statically) |
| `utils/helper_api.py` | 99 | 0 | 1 | tests-only |
| `utils/sql_utils.py` | 196 | 0 | 4 | tests-only facade: retire after migrating 4 test files |
| `utils/csv_utils.py` | 871 | 5 | 1 | live; mixed responsibilities |
| `utils/parsing_utils.py` | 1217 | 1 | 1 | live; very large |
| `utils/monitor_utils.py` | 131 | 1 | 0 | live; JSON dedup state, no tests |
| `utils/update_utils.py` | 54 | 1 (`on_message`) | 0 | live; runtime git self-update |
| `utils/policy_resolver.py` | 804 | 4 | 2 | live; canonical policy engine candidate |
| `utils/openai_utils.py` | 274 | 2 | 1 | live; optional LLM path |

The proposal's claims about the first three modules and `sql_utils` check out; `helper_api.py` is not referenced by production code either, only by one test. Not examined: whether `helper_api.py`'s classifier and `policy_resolver.py` disagree on real announcements (the proposal asserts it; I did not test it).

Other things noted but not classified: `scripts/env_gui.py` (config GUI that also submits "Codex change requests"), `scripts/run-rsassistant-hardening.sh` (runs the retired hardening train), `scripts/apply-auto-rsa-patch.sh` + `patches/` (redundant with the fork), `scripts/migrate_json_to_sql.py` (one-time), `backups/` (4 KB), `.omx/`, `.codex/`, `.agents/` tool directories, 100+ stale remote branches (many `codex/*` and dated feature branches).

---

## 8. Corrections / confirmations to the proposed architecture

| Claim in the proposal | Local finding |
|---|---|
| Fork is 2 ahead / 0 behind upstream | **Confirmed** (after fetching upstream). |
| Compose builds auto-rsa from a local checkout absent from the repo | **Confirmed**: `./auto-rsa` is gitignored and a standalone git repo; additionally its `src` is bind-mounted over the image, so the image alone does not determine behaviour. |
| `production` branch 516 behind / 1 ahead; unclear which is run | **Resolved**: neither; `production` is abandoned (May 2025). Runs from the local `main` working tree. |
| "Complete TP-20261013-001 first" | **Already complete and deployed** (plus 002). Migration step 02 is satisfied. |
| 36 commands in nine cogs | ~39 commands in ten cogs now (my additions). Count is for text-prefix `..` commands only. |
| Cooperation happens via Discord commands, parsed responses and shared files | **Confirmed**, with the added detail that the file path is a fork patch writing a merged JSON per broker, and that ULT-MA presumes an auto-rsa HTTP API. |
| Need `AutoRSA-GUI` / local dashboard info | **Found**: two GUI forks (Arch and web), one with uncommitted broker edits, plus an inactive systemd unit; see §4. |
| Single `fun_run()` handles broker selection, auth, holdings, trading, Discord | `src/auto_rsa.py` is 499 lines; I did not read `fun_run` itself, so neither confirmed nor refuted. Fork `src/brokers.py` and `src/cli.py` also exist. |

---

## 9. Open questions and unverified items (need the owner or deeper inspection)

1. **Why does `OrderHistory` stop at 2026-07-30 while sends continue?** Candidates: `SQL_LOGGING_ENABLED` unset/false in live env (the flag is not in `config/.env`; its default in `config_utils.py` was not checked), changed auto-rsa reply format since July, parser regression, or the fork's response text. Needs a log trace of a recent `!rsa buy` round trip. *This is the single most important fact for designing a fill-reconciliation layer, since the legacy system apparently cannot currently tell a send from a fill.*
2. **`holdings_current` has 1 row and `holdings_refreshes` has 0** while `HoldingsLive` has 81k rows and the JSON snapshot has 557 entries. Is the SQL "current holdings" contract actually being used in production, or is it staged/finalized differently than the tests assume?
3. **Which brokers does the owner actually trade and require?** Data suggests Fidelity, Robinhood, Fennel, Public, Wells Fargo, Vanguard, Webull, BBAE, DSPAC (+ Chase credentials, minimal Schwab). Confirm, and confirm what to drop from the 16 adapters.
4. **Does the fork expose an HTTP API for ULT-MA's `TradeExecutor`?** `plugins/ultma/executor.py` calls "auto-rsa's HTTP API"; no such server was found in the fork's `src` listing. `ENABLED_PLUGINS` is unset in live `.env`, so ULT-MA is presumably off. Confirm whether ULT-MA is still wanted.
5. **Which copy of Chase/Fennel/Wells Fargo code is authoritative?** `AutoRSA-GUI.local` has uncommitted edits; the modern fork has a Wells Fargo rewrite and untested Chase/Fennel. Needs a per-broker diff.
6. **Who restarted the stack at 23:43 ET today** (containers show `Created 2026-10-16T03:43Z`)? There may be an unseen automation (cron/hook/Watchtower profile) that rebuilds from the working tree; if so, any WIP on disk can reach production unreviewed.
7. **Is the Discord identity shared?** `autorsa-gui.service` (inactive) and the container both run an "auto-rsa bot"; confirm they never run simultaneously with the same token.
8. **Credentials hygiene:** `auto-rsa/creds/` holds JSON and a Robinhood `.pickle` session; `auto-rsa/did.bin`, `AutoRSA-GUI.local/did.bin`, and a `Portfolio_Positions_Aug-03-2026.csv` (23 KB) sit in the fork directory. Check `.gitignore` of the fork covers them (the fork's `.gitignore` is 220 bytes). Not verified.
9. **Backups:** only an ad-hoc DB copy (`*.bak-20261010-pre-backfill`) was seen; no scheduled backup job found. Today's v10 migration ran on production without an automated backup. A pre-migration backup of `rsa_database.db` and `creds/` is advisable before any further schema work.
10. **Python version skew:** CI 3.12, RSAssistant image 3.12, auto-rsa image 3.14.3, local venv 3.14. Relevant to any shared-package design.
11. **Backfill of account value history** (`backfill_historical_account_values`) was noted in the tracker as never run in production; the `.bak-20261010-pre-backfill` suggests it was run on 2026-10-10 (snapshots table has 3,714 rows). Status not confirmed.
12. The four open split watches (BTOC today, KNDI, FRGT, OBAI) are **live trading state**; any migration cutover has to carry them (and `split_monitor_accounts` marks) across, or finish them first.

---

## 10. Suggested inputs for the migration design (derived, not decisions)

- Treat the **freeze/inventory** step as mostly done by this document; the remaining pre-work is items 1, 2, 5 and 9 in §9.
- A **pre-migration safety set**: tag current `main` and `auto-rsa@110439c`; snapshot `rsa_database.db` (WAL-safe `.backup`), `config/`, `auto-rsa/creds/`, `auto-rsa/.env`; commit or archive `AutoRSA-GUI.local` dirty edits to a branch; push my two local commits (`88d2798`, `001e425`) if desired.
- The **adapter priority** should come from §5 usage: Fidelity first (most custom code and tests, 126 positions, 223 orders), then Robinhood/Fennel/Public (largest position counts), then Wells Fargo, Webull, BBAE, DSPAC, Vanguard.
- The first useful **read-only shadow target** is the existing `auto_rsa_holdings.json` pipeline: it already has per-broker replace semantics, so a new adapter can be compared snapshot-for-snapshot against it.
- The new design must replace the **text-in/text-out Discord coupling** at three exact seams: `!rsa buy/sell` emission (`utils/order_exec.py`, `rsassistant/services/order_orchestration.py`, `cogs/orders.py`, `services/alert_processing.py`), `!rsa holdings` emission (`cogs/holdings.py`, `utils/watch_utils.py`), and response parsing (`on_message.py`, `utils/parsing_utils.py`). Each also feeds `rsa_order_send_log` / `OrderHistory`, which is where the send-vs-fill gap from §0.5 lives.
- Existing guarantees to carry forward as invariants/tests: the idempotent split-event claim, `needs_reconciliation` on unknown outcomes, single order dispatcher with atomic state claims (`pending → dispatching`, `needs_review` instead of re-send), fail-closed date handling, and the SQLite-only mutable-state rule.

---

## Appendix: commands used (all read-only)

`git status/log/rev-list/remote/diff --stat`, `docker ps/inspect/images/logs`, `sqlite3 ... mode=ro` aggregate queries (counts/min/max only), `grep -r` for callers/env key names, `ls`/`du`, `diff -rq` between the two auto-rsa clones. Test runs earlier in the session used a scratch `VOLUMES_DIR`.
