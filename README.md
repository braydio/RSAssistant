# RSAssistant

RSAssistant is a Discord bot that monitors reverse split announcements and automates trading workflows around them. It parses NASDAQ/SEC alerts, maintains watchlists, and sends `!rsa` commands to autoRSA for execution.

## What it does

- Monitors secondary-channel alert feeds for reverse split announcements.
- Extracts dates, ratios, and fractional share policies from filings.
- Maintains watch and sell lists, reminders, and scheduled orders.
- Refreshes holdings via `..all`, audits them against the watchlist, and posts consolidated summaries.
- Persists logs, Excel output, and a SQLite database under `volumes/` (override with `VOLUMES_DIR`).

## Minimal configuration quickstart

1. Copy the example env file:

```bash
cp config/.env.example config/.env
```

2. Open `config/.env` and set at least:

- `BOT_TOKEN`
- `DISCORD_PRIMARY_CHANNEL`
- `DISCORD_SECONDARY_CHANNEL`
- `DISCORD_TERTIARY_CHANNEL` (optional, falls back to primary)

3. Start the bot:

```bash
python RSAssistant.py
```

That is enough to run the core workflow. See the sections below for optional OpenAI parsing, holdings alerts, and refresh automation.

## Setup (local)

```bash
git clone https://github.com/braydio/RSAssistant.git
cd RSAssistant
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.example config/.env
python RSAssistant.py
```

## Setup (Docker)

```bash
cp config/.env.example config/.env
docker compose up --build
```

Docker uses `config/.env` via compose `env_file`. The application does not load a `.env` file inside the container.

## Discord channel layout

- `DISCORD_PRIMARY_CHANNEL`: Operational commands, holdings refresh output, order confirmations.
- `DISCORD_SECONDARY_CHANNEL`: Where NASDAQ/SEC alert feeds are posted.
- `DISCORD_TERTIARY_CHANNEL`: Reverse split summaries and policy snippets (optional).

If `DISCORD_TERTIARY_CHANNEL` is not set, summaries fall back to the primary channel.

## Configuration notes

### Env file loading

- Default: `config/.env` when running locally.
- Override: set `ENV_FILE=/path/to/your.env`.
- Docker: process environment only (compose `env_file`).

### OpenAI policy parsing (optional)

Set these in `config/.env` to enable LLM tie-breakers:

- `OPENAI_POLICY_ENABLED=true`
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-4o-mini` (default)

### Holdings refresh and alerts

- `AUTO_REFRESH_ON_REMINDER` (bool): Send `!rsa holdings all` after reminders.
- `ENABLE_MARKET_REFRESH` (bool): Run `..all` every 15 minutes during market hours.
- `HOLDING_ALERT_MIN_PRICE` (float): Minimum last price to trigger alerts (default `1`).
- `AUTO_SELL_LIVE` (bool): Also post `!rsa sell {quantity} {ticker} {broker} false`.
- `IGNORE_TICKERS` / `IGNORE_TICKERS_FILE`: Skip alert/auto-sell for tickers.
- `IGNORE_BROKERS` / `IGNORE_BROKERS_FILE`: Skip alert/auto-sell for brokers.
- `MENTION_USER_ID` / `MENTION_USER_IDS`: Discord user IDs to mention.
- `MENTION_ON_ALERTS` (bool): Enable/disable mentions.

Example ignore list:

```bash
cp config/ignore_tickers.example.txt config/ignore_tickers.txt
echo "AAPL" >> config/ignore_tickers.txt
```

### Market holidays

```bash
cp config/market_holidays.example.txt config/market_holidays.txt
echo "2025-01-01  # New Year's Day" >> config/market_holidays.txt
```

## Feeds

Point your RSS relay (for example, MonitoRSS) at:

- `https://nasdaqtrader.com/Rss.aspx?feed=currentheadlines&categorylist=105`
- `https://www.revrss.com/newswires.xml`

Post these into the channel mapped to `DISCORD_SECONDARY_CHANNEL`.

## Architecture overview

- `RSAssistant.py` launches the modular runtime in `rsassistant/bot`.
- `rsassistant/` contains Discord cogs, handlers, and background tasks.
- `utils/` contains configuration, parsing, scheduling, and persistence helpers.
- Runtime state lives under `volumes/` (logs, DB, Excel, split watchlist).

Directory snapshot:

```
.
├── RSAssistant.py
├── rsassistant/            # Bot runtime and cogs
├── utils/                  # Shared helpers
├── config/                 # .env and config files
├── volumes/                # Logs, database, Excel output
├── unittests/              # Unit tests
├── requirements.txt
├── docker-compose.yml
└── Dockerfile
```

## Default account nicknames

If a broker/account is missing from `config/account_mapping.json`, RSAssistant falls back to the pattern `"{broker} {group} {account}"` and writes it to the mapping file so tracking still works.

## Testing

```bash
python -m unittest discover -s unittests -p '*_test.py'
```

## Contributing

Follow the repository guidelines in `AGENTS.md`, especially around config, logging, and where to place new code.
