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
- `excel/` (legacy archive only; no runtime writes)

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
2. LLM parsing uses the OpenAI Responses API with a strict JSON schema and fills
   only missing facts supported by evidence from the notice.
3. Programmatic/LLM conflicts are retained for review and prevent automation.
4. A matching ticker, confirmed reverse split, explicit upward rounding,
   effective date, and split ratio are required before watchlist automation.

Source cleanup preserves the complete extracted article before the request-level
passage selector applies its character budget, so exact evidence is not damaged
at the start of the article. Evidence validation failures are retained as
specific field-level rejection reasons for operator diagnostics.

Nasdaq Trader source discovery prefers the mobile `TraderNews.aspx` endpoint and
validates its visible notice content before parsing. This prevents HTTP-200 bot
challenge pages from being mistaken for notices. Press-release and SEC link
parsers reuse that single response, with the canonical desktop endpoint retained
as a fallback.

## Plugins

Enable plugins via `ENABLED_PLUGINS` (comma-separated). Each plugin exposes a
`setup()` entrypoint under `plugins/<name>/` and can register its own cogs/tasks.

See `plugins/ultma/README.md` for configuration details.
