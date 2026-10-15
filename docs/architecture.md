# RSAssistant Architecture

## Runtime flow

```
RSAssistant.py
  -> rsassistant/bot/core.py (bot setup + plugin loading)
    -> cogs + background tasks
      -> utils/ (parsing, policy resolution, scheduling, persistence)
      -> volumes/ (DB, CSV logs, legacy archives)
```

## Module boundaries

- `rsassistant/`: Discord-facing orchestration, cogs, and tasks.
- `utils/`: Pure helpers and shared business logic (no Discord I/O).
- `plugins/`: Optional extensions loaded via `ENABLED_PLUGINS`.
- `externalization-staging/`: Experimental utilities slated for extraction.

## Data locations

All runtime state lives under `VOLUMES_DIR` (default `./volumes`):

- `db/` (SQLite DB, split watchlist, order queue, auto-rsa holdings snapshot)
- `logs/` (application logs + CSV exports such as holdings/orders)

## Local operations UI

`scripts/env_gui.py` provides a local-only web UI for editing `config/.env` and now includes a Codex request panel that can invoke `codex exec` with operator-entered change instructions.

## Auto-rsa integration

RSAssistant does not import auto-rsa code. It communicates via Discord commands
and can optionally ingest a holdings snapshot JSON file if auto-rsa writes it to
a shared path (`AUTO_RSA_HOLDINGS_FILE`).

When `AUTO_RSA_ERROR_WATCHER_ENABLED=true`, RSAssistant also monitors the
primary Discord channel for error-like messages and invokes `codex exec` with
runtime context so Codex can attempt automatic remediation in `AUTO_RSA_DIR`
(or provide a manual summary/patch when write access is unavailable).

## Policy parsing

1. Programmatic parsing runs when `PROGRAMMATIC_POLICY_ENABLED=true`.
2. LLM parsing runs when `OPENAI_POLICY_ENABLED=true` and fills in missing details.
3. The resolved policy + effective date drive watchlist scheduling and reminders.

## Plugins

Enable plugins via `ENABLED_PLUGINS` (comma-separated). Each plugin exposes a
`setup()` entrypoint under `plugins/<name>/` and can register its own cogs/tasks.

See `plugins/ultma/README.md` for configuration details.

## Price cache

`utils/price_fetcher.py` caches yfinance prices in memory and in `volumes/cache/yfinance_price_cache.json`. Entries are fresh for 10 minutes (`TTL_SECONDS`); a failed refresh still returns the prior cached price (legacy behavior) until it is 30 days old, then it is dropped. The cache holds at most `PRICE_CACHE_MAX_ENTRIES` symbols (default 1,000, oldest timestamp evicted first). The file is rewritten atomically (temp file + `os.replace`) only after a refresh that changed prices, and malformed or non-finite entries are ignored on load. Concurrent threads asking for the same symbol share one fetch.

## Container image and health

The `Dockerfile` is a two-stage build (`python:3.12-slim`): dependencies are installed into an isolated prefix in the builder stage and only that prefix, `git` (needed by `utils/update_utils.py`) and the app source reach the runtime image. `.dockerignore` keeps runtime state (`volumes/`), credentials, local trees (`auto-rsa*`, `*.local`, backups) and tests out of the build context. `entrypoint.sh` creates missing `logs/`, `db/`, `cache/` directories (mode 755 only on directories it creates) and never walks existing data; it does not set `DISPLAY`. The Docker healthcheck runs `scripts/healthcheck.py`, which fails when `logs/heartbeat.txt` is missing, empty, or older than `HEARTBEAT_MAX_AGE_SECONDS` (default 180s, three heartbeat intervals); it only reads the file.

## Runtime artifact hygiene

`volumes/**` is git-ignored (only `volumes/db/README.md` and the sample XLSX are allowlisted) and excluded from the Docker context. `python scripts/audit_runtime_artifacts.py` inventories error captures, rotated logs, active logs and cache files under `VOLUMES_DIR` without changing anything. `--prune --older-than-days N` (N >= 1) deletes only expendable files: `db/fidelity_errors/*.html|png`, rotated `logs/*.log.<n>`, and stale `cache/*.tmp`. Databases, WAL/SHM, holdings/order audit logs, CSV logs, active logs and backups are never candidates, and symlinks are never followed. Error captures are emitted by the auto-rsa container into the shared `volumes/db`, so no retention env var is defined here.
