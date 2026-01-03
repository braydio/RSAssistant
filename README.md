# RSAssistant

RSAssistant is a Discord bot that monitors corporate actions and automates trading tasks around reverse stock splits. It parses NASDAQ and SEC alerts, tracks watchlists, and schedules orders to run through [autoRSA by NelsonDane](https://github.com/NelsonDane/auto-rsa).

## Features

- Monitors NASDAQ and SEC feeds for reverse split announcements.
- Parses filings and press releases for fractional share policies and effective dates.
- Maintains watch and sell lists with automatic reminders.
- Schedules buy or sell orders and executes them via autoRSA.
- The `..all` command refreshes holdings, audits them against the watchlist,
  and posts a summary of any missing tickers alongside a consolidated broker
  holdings status embed.
- Stores logs and a SQLite database under `volumes/` for persistence. Set
  the `VOLUMES_DIR` environment variable to use a different location (e.g.
  `/mnt/netstorage/volumes`).

### Persistent logging toggles

CSV, Excel, and SQL persistence are enabled by default. To disable any of
these logging layers, set the corresponding environment variable to `false`:

- `CSV_LOGGING_ENABLED`
- `EXCEL_LOGGING_ENABLED`
- `SQL_LOGGING_ENABLED`

Any value other than `false` leaves the logger enabled.

### Daily Holdings Refresh + Over-$1 Monitor

RSAssistant can optionally trigger a holdings refresh when a watchlist reminder is posted, then watch incoming holdings embeds and alert on positions meeting a price threshold. It can also optionally auto-sell those positions.

When `ENABLE_MARKET_REFRESH=true`, the bot also schedules the ``..all`` total refresh command every 15 minutes during U.S. market hours while continuing to run at 8:00 AM and 8:00 PM Eastern outside of market hours. Without the toggle, the two out-of-hours runs remain so you can opt out of the higher-frequency cadence. Weekend and configured market-holiday dates are skipped for automated refreshes/reminders, and scheduled orders are only sent during market hours.

### Watchlist commands

- `..watch`: Add one or more tickers to the watchlist using either the
  traditional ``..watch TICKER mm/dd [ratio]`` format or the bulk lines format
  such as ``TICKER 1-10 (purchase by 10/24)``.
- `..watchlist`: Display all tracked tickers with their split dates and ratios (no prices).
- `..watchprices`: Display the watchlist with split info and the latest pulled prices.
- `..prices`: List only the latest prices for tickers on the watchlist.

- Auto refresh on reminder: posts `!rsa holdings all` after the reminder
- Over-threshold alert: posts a note in the primary Discord channel
- Optional auto-sell: posts a `!rsa sell {quantity} {ticker} {broker} false`
- Daily de-dupe: avoids repeat alerts/sells per broker/account/ticker per day

Configure these via environment variables (see below).

## Directory Overview

```
.
├── RSAssistant.py           # Main bot application
├── utils/                   # Helper modules and order management
├── config/                  # Example env and settings files
├── volumes/                 # Logs, database, and Excel output
├── unittests/               # Test suite
├── requirements.txt         # Python dependencies
├── docker-compose.yml       # Docker setup
└── Dockerfile
```

`RSAssistant.py` initializes the bot, command handlers, and scheduled tasks. Utility modules under `utils/` handle configuration, watch lists, and order execution.

### Code ownership

- `rsassistant/`: Discord orchestration (cogs, tasks, bot startup).
- `utils/`: Pure helpers without Discord context (parsing, storage, scheduling, config).

## Quick Start

1. Clone the repository and install dependencies:

```bash
git clone https://github.com/braydio/RSAssistant.git
cd RSAssistant
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy the example configuration and update your Discord credentials:

```bash
\# Single source of truth for configuration
cp config/example.env config/.env
```

If you want RSAssistant to store data in an external location, set the
`VOLUMES_DIR` variable in your environment (for local and Docker) to your
desired path.

3. Point your Discord RSS relay (e.g., MonitoRSS) at the reverse split feeds
   so RSAssistant can parse new notices from your secondary channel:

   - `https://nasdaqtrader.com/Rss.aspx?feed=currentheadlines&categorylist=105`
   - `https://www.revrss.com/newswires.xml`

   Post these feeds into the channel mapped to `DISCORD_SECONDARY_CHANNEL`; the
   bot will mirror parsed reverse split summaries and policy notes to the
   tertiary channel when configured.

4. Launch the bot:

```bash
python RSAssistant.py
```

The bot's `..all` command now audits your holdings against the watchlist,
summarizes any tickers that are missing from your accounts, and consolidates
broker holdings status into a single embed.

## How to Run

CLI:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/example.env config/.env
python RSAssistant.py
```

Docker:

```bash
cp config/example.env config/.env
docker compose up --build
```

Optional: set `OPENAI_POLICY_ENABLED=true` and `OPENAI_API_KEY=...` in
`config/.env` to enable OpenAI reverse-split parsing.

### Discord channel configuration

RSAssistant differentiates between three Discord channels so information lands
where it is most actionable:

- `DISCORD_PRIMARY_CHANNEL`: Operational commands, holdings refresh output, and
  scheduled order confirmations.
- `DISCORD_SECONDARY_CHANNEL`: Source feed where NASDAQ and SEC alerts arrive.
- `DISCORD_TERTIARY_CHANNEL`: Destination for reverse split summaries and the
  associated policy snippets parsed from filings or press releases.

Populate the corresponding environment variables in your `.env` file with the
channel IDs for your server. When the tertiary channel ID is omitted, the bot
falls back to the primary channel to avoid dropping critical alerts.

### Configuration: Auto Refresh + Monitor

Add the following keys to your environment. The app now loads from a single source:

- Local default: `config/.env`
- Override: set `ENV_FILE=/path/to/your.env` when running locally
- Docker: compose injects variables from `config/.env`; the app does not load a file in-container

- `AUTO_REFRESH_ON_REMINDER` (bool): If `true`, send `!rsa holdings all` after the reminder fires. Default `false`.
- `HOLDING_ALERT_MIN_PRICE` (float): Minimum last price to trigger the alert. Default `1`.
- `AUTO_SELL_LIVE` (bool): If `true`, also post `!rsa sell {quantity} {ticker} {broker} false`. Default `false`.
- `ENABLE_MARKET_REFRESH` (bool): If `true`, schedule the ``..all`` command every
  15 minutes during market hours in addition to the 8:00 AM and 8:00 PM runs.
  Default `false` to avoid the higher-frequency cadence unless explicitly
  requested.
- `MARKET_HOLIDAYS_FILE` (path, optional): File containing market holidays (one `YYYY-MM-DD` per line). Defaults to `config/market_holidays.txt`. Lines starting with `#` are treated as comments.
- `IGNORE_TICKERS` (CSV): Tickers to skip for alert/auto-sell (e.g., `ABCD,EFGH`). Default empty.
- `IGNORE_TICKERS_FILE` (path, optional): File containing one ticker per line to ignore. Defaults to `config/ignore_tickers.txt`. Lines starting with `#` are treated as comments.
- `IGNORE_BROKERS` (CSV): Brokers to skip for alert/auto-sell (e.g., `Fidelity,Schwab`). Default empty.
- `IGNORE_BROKERS_FILE` (path, optional): File containing one broker name per line to ignore. Defaults to `config/ignore_brokers.txt`. Lines starting with `#` are treated as comments.

You can use either the env var, the file, or both — the sets merge. Create the file like:

```
cp config/ignore_tickers.example.txt config/ignore_tickers.txt
echo "AAPL" >> config/ignore_tickers.txt
echo "MSFT  # Long-term" >> config/ignore_tickers.txt
```

Apply the same approach for brokers by creating `config/ignore_brokers.txt`
with one broker name per line.

To configure market holidays, copy the example list and add your dates:

```
cp config/market_holidays.example.txt config/market_holidays.txt
echo "2025-01-01  # New Year's Day" >> config/market_holidays.txt
```

- `MENTION_USER_ID` / `MENTION_USER_IDS` (string or CSV): Discord user ID(s) to @-mention in alerts (e.g., `123456789012345678` or `123...,987...`). Optional.
- `MENTION_ON_ALERTS` (bool): Enable/disable mentions on alerts. Default `true`.

De-duplication state is stored at `config/overdollar_actions.json`. Delete that file if you want to reset daily state immediately.

### Docker

Alternatively, build and run with Docker:

```bash
docker compose up --build
```

The compose setup also includes a `watchtower` container which checks for new
images daily and automatically updates the running `rsassistant` service.

Environment loading behavior inside Docker:

- Compose uses `env_file: config/.env` and passes variables to the container.
- The application detects it is running in Docker and relies on the process environment only (no additional `.env` file is read inside the container).

To run locally with a custom env file path instead of `config/.env`, prefix commands with:

```bash
ENV_FILE=config/.env python RSAssistant.py
```

`RSAssistant.py` launches the modular bot implementation under `rsassistant/bot`.

## Default Account Nicknames

When an account has no nickname in `account_mapping.json`, RSAssistant falls
back to the pattern `"{broker} {group} {account}"`. This ensures new accounts
and orders are always logged with a deterministic identifier.

## Testing

Run unit tests with:

```bash
python -m pytest
```

Tests rely on `pytest` for fixtures and discovery.

## License

This project is released under the MIT License.
