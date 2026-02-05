# RSAssistant Architecture

## Runtime flow

```
RSAssistant.py
  -> rsassistant/bot/core.py (bot setup + plugin loading)
    -> cogs + background tasks
      -> utils/ (parsing, policy resolution, scheduling, persistence)
      -> volumes/ (DB, logs, Excel output)
```

## Module boundaries

- `rsassistant/`: Discord-facing orchestration, cogs, and tasks.
- `utils/`: Pure helpers and shared business logic (no Discord I/O).
- `plugins/`: Optional extensions loaded via `ENABLED_PLUGINS`.
- `externalization-staging/`: Experimental utilities slated for extraction.

## Data locations

All runtime state lives under `VOLUMES_DIR` (default `./volumes`):

- `db/` (SQLite DB, split watchlist, order queue, auto-rsa holdings snapshot)
- `logs/` (application + holdings logs)
- `excel/` (ReverseSplitLog.xlsx)

## Policy parsing

1. Programmatic parsing runs when `PROGRAMMATIC_POLICY_ENABLED=true`.
2. LLM parsing runs when `OPENAI_POLICY_ENABLED=true` and fills in missing details.
3. The resolved policy + effective date drive watchlist scheduling and reminders.

## Plugins

Enable plugins via `ENABLED_PLUGINS` (comma-separated). Each plugin exposes a
`setup()` entrypoint under `plugins/<name>/` and can register its own cogs/tasks.

See `plugins/ultma/README.md` for configuration details.
