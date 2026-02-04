# RSAssistant

RSAssistant is a Discord bot that monitors reverse split announcements and automates trading workflows around them. It parses NASDAQ/SEC alerts, maintains watchlists, and sends `!rsa` commands to auto-rsa for execution.

## Key features

- Monitors secondary-channel alert feeds for reverse split announcements.
- Extracts dates, ratios, and fractional share policies from filings.
- Maintains watch and sell lists, reminders, and scheduled orders.
- Refreshes holdings via `..all`, audits them against the watchlist, and posts consolidated summaries.
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
- `volumes/excel/` (ReverseSplitLog.xlsx)

Watchlist, sell list, and account mappings now live in the SQLite database
(`watchlist`, `sell_list`, and `account_mappings` tables). Legacy JSON files can
be migrated once via `..loadmap` (for account mappings) or automatically on
startup when SQL logging is enabled.

## Auto-rsa holdings import (recommended)

If auto-rsa writes a JSON snapshot to a shared volume, RSAssistant can ingest it directly:

- `AUTO_RSA_HOLDINGS_ENABLED=true`
- `AUTO_RSA_HOLDINGS_FILE=volumes/db/auto_rsa_holdings.json`

RSAssistant polls for changes and updates `volumes/logs/holdings_log.csv`.

### Auto-rsa patch quickstart (holdings snapshot file)

You do not need to clone auto-rsa inside this repo. The patch can be applied in any
auto-rsa clone as long as both containers share a volume.

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
