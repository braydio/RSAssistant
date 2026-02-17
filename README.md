# RSAssistant

RSAssistant is a Discord bot that monitors reverse split announcements and automates trading workflows around them. It parses NASDAQ/SEC alerts, maintains watchlists, and sends `!rsa` commands to auto-rsa for execution.

## Key features

- Monitors secondary-channel alert feeds for reverse split announcements.
- Extracts dates, ratios, and fractional share policies from filings.
- Maintains watch and sell lists, reminders, and scheduled orders.
- Refreshes holdings via `..all`, audits them against the watchlist, posts consolidated summaries, and can queue watchlist autobuys for missing broker positions.
- Persists logs, watchlists, and account mappings in SQLite under `volumes/` (override with `VOLUMES_DIR`).

## Quickstart (local)

```bash
cp config/.env.example config/.env
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python RSAssistant.py
```

## Quickstart (Docker)

```bash
cp config/.env.example config/.env
docker compose up --build
```

Docker uses the environment provided by Compose (`env_file` / `environment`). The
application does not load a `.env` file inside the container.

## Configuration basics

Required settings in `config/.env`:

- `BOT_TOKEN`
- `DISCORD_PRIMARY_CHANNEL`
- `DISCORD_SECONDARY_CHANNEL`

Optional channels:

- `DISCORD_TERTIARY_CHANNEL` (summaries; falls back to primary)
- `DISCORD_HOLDINGS_CHANNEL` (auto-rsa holdings embeds)
- `DISCORD_WATCHLIST_CHANNEL` (watchlist-only output)
- `AUTO_BUY_WATCHLIST` (when `true`, `..all` queues `!rsa buy 1 <ticker> <broker> false` if a watched ticker is missing and no queued order exists)

Env file loading order:

1. `ENV_FILE=/absolute/or/relative/path.env` (only this file is loaded)
2. Docker: process environment only
3. Local default: `config/.env`

## Optional env GUI

```bash
python scripts/env_gui.py
```

Then open `http://127.0.0.1:8765` in your browser.

## Policy parsing flow

1. Programmatic parsing (NASDAQ/SEC/press release) runs when `PROGRAMMATIC_POLICY_ENABLED=true`.
2. LLM parsing runs when `OPENAI_POLICY_ENABLED=true` and can fill in missing ratio/date/policy details.
3. The resolved policy and effective date drive watchlist scheduling and reminders.

## Data & persistence

Runtime state lives under `VOLUMES_DIR` (default `./volumes`):

- `volumes/db/` (SQLite DB, order queue, auto-rsa holdings snapshot)
- `volumes/logs/` (app logs, holdings logs)
- `volumes/excel/` (legacy archive only; Excel writes are deprecated)

Watchlist, sell list, and account mappings now live in the SQLite database
(`watchlist`, `sell_list`, and `account_mappings` tables). Legacy JSON files are
migrated automatically on startup when SQL logging is enabled (only when the
matching SQL tables are empty), and can also be migrated manually with:

### Migration note for legacy Excel users

If your workflow previously depended on `volumes/excel/ReverseSplitLog.xlsx`,
use SQL and CSV outputs instead:

- Account mappings/watchlist/sell list are read from SQLite (`volumes/db/`).
- Operational logs are emitted as CSV files in `volumes/logs/` (for example
  holdings and orders logs).
- `volumes/excel/` is retained only as an archive and is not updated at runtime.


```bash
python scripts/migrate_json_to_sql.py
# optional: archive imported JSON files to *.migrated
python scripts/migrate_json_to_sql.py --archive
```

## Auto-rsa holdings import (recommended)

If auto-rsa writes a JSON snapshot to a shared volume, RSAssistant can ingest it directly:

- `AUTO_RSA_HOLDINGS_ENABLED=true`
- `AUTO_RSA_HOLDINGS_FILE=volumes/db/auto_rsa_holdings.json`

RSAssistant polls for changes and updates `volumes/logs/holdings_log.csv`.

RSAssistant validates holdings CSV schema during ingest (required/exact columns and numeric/timestamp coercion). If the file or rows are invalid, ingest is rejected and SQL state is not updated.

### Auto-rsa patch quickstart (holdings snapshot file)

You do not need to clone auto-rsa inside this repo. The patch can be applied in any
auto-rsa clone as long as both containers share a volume. RSAssistant does not import
auto-rsa code directly; it only sends Discord commands and optionally reads the shared
holdings snapshot file.

```bash
git clone git@github.com:NelsonDane/auto-rsa.git
cd auto-rsa
git apply /path/to/RSAssistant/patches/auto-rsa-holdings.patch
```

Or use the helper script from this repo:

```bash
./scripts/apply-auto-rsa-patch.sh /path/to/auto-rsa
```

The patcher reads `AUTO_RSA_HOLDINGS_FILE` from your environment (or
`config/.env`) and writes it into the auto-rsa `.env` (override with
`AUTO_RSA_ENV_FILE=/path/to/auto-rsa.env`). Then set the same
`AUTO_RSA_HOLDINGS_FILE` value in RSAssistant so both containers share the
snapshot path.

You can also run the patcher from Discord (admin-only):

```bash
..patchautorsa /path/to/auto-rsa
```

### Local layout (optional)

If you prefer keeping the repos near each other locally, use sibling folders and a
shared `volumes/` directory (or Docker volume). Example:

```
/home/braydenchaffee/Trading/
  RSAssistant/
  auto-rsa/
  AutoRSA-GUI/
  shared/
    volumes/
      db/auto_rsa_holdings.json
      logs/
      excel/
```

Point both apps at the same `AUTO_RSA_HOLDINGS_FILE` path. `AutoRSA-GUI` is optional
and is not referenced by RSAssistant.

### Version control options for local clones

- Recommended: keep `auto-rsa/` and `AutoRSA-GUI/` as separate repos (outside this repo).
- If you keep them inside this repo for convenience, either:
  - Add them as git submodules, or
  - Add them to `.gitignore` so credentials and binaries are not tracked.

## Holdings snapshots

Use `..snapshot` to post a holdings snapshot to the holdings channel. Provide a
broker name to focus on one brokerage or a number to change the top-positions
count:

```bash
..snapshot
..snapshot webull
..snapshot webull 5
..snapshot 8
```


## Sent order audit trail

RSAssistant now records each outbound `!rsa` order command with send time, ticker,
action, quantity, broker, and destination channel in `volumes/db/order_send_log.json`.

Use Discord commands to inspect this data:

```bash
..orders
..orders 20
..orders TSLA
..orders TSLA sell
..lastorder
..lastorder TSLA
```

`..orders` supports lightweight filtering by optional limit (max 50), ticker, and
action (`buy`/`sell`).

## Plugins

Plugins are opt-in via `ENABLED_PLUGINS` (comma-separated). The ULT-MA plugin ships
with the repo and can be enabled with:

```bash
ENABLED_PLUGINS=ultma
```

See `plugins/ultma/README.md` for configuration and commands.

## Feeds

Point your RSS relay (for example, MonitoRSS) at:

- `https://nasdaqtrader.com/Rss.aspx?feed=currentheadlines&categorylist=105`
- `https://www.revrss.com/newswires.xml`

Post these into the channel mapped to `DISCORD_SECONDARY_CHANNEL`.

## Architecture overview

- `RSAssistant.py` launches the modular runtime in `rsassistant/bot`.
- `rsassistant/` contains Discord cogs, handlers, and background tasks.
- `utils/` contains configuration, parsing, scheduling, and persistence helpers.
- Runtime state lives under `volumes/` (logs and the SQLite DB).

Directory snapshot:

```
.
├── RSAssistant.py
├── rsassistant/            # Bot runtime and cogs
├── utils/                  # Shared helpers
├── config/                 # .env and config files
├── volumes/                # Logs, database, watchlist output
├── unittests/              # Unit tests
├── requirements.txt
├── docker-compose.yml
└── Dockerfile
```

## Default account nicknames

If a broker/account is missing from SQL account mappings, RSAssistant falls back to the pattern `"{broker} {group} {account}"` and stores it in the `account_mappings` table so tracking still works. Legacy JSON mappings can be migrated with `..loadmap`.

## Testing

```bash
python -m unittest discover -s unittests -p '*_test.py'
```

## Contributing

Follow the repository guidelines in `AGENTS.md`, especially around config, logging,
and where to place new code.
