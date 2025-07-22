# RSAssistant

RSAssistant is a Discord bot that monitors corporate actions and automates trading tasks around reverse stock splits. It parses NASDAQ and SEC alerts, tracks watchlists, and schedules orders to run through [autoRSA](https://github.com/NelsonDane/autoRSA).

## Features

- Monitors NASDAQ and SEC feeds for reverse split announcements.
- Parses filings and press releases for fractional share policies.
- Maintains watch and sell lists with automatic reminders.
- Schedules buy or sell orders and executes them via autoRSA.
- The `..all` command refreshes holdings, audits them against the watchlist,
  and posts a summary of any missing tickers.
- Stores logs and a SQLite database under `volumes/` for persistence.

## Directory Overview

```
.
├── RSAssistant.py           # Main bot application
├── utils/                   # Helper modules and order management
├── config/                  # Example env and settings files
├── volumes/                 # Logs, database, and Excel output
├── docker-compose.yml       # Docker setup
└── Dockerfile
```

`RSAssistant.py` initializes the bot, command handlers, and scheduled tasks. Utility modules under `utils/` handle configuration, watch lists, and order execution.

## Quick Start

1. Clone the repository and install dependencies:

```bash
git clone https://github.com/your-org/RSAssistant.git
cd RSAssistant
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy the example configuration and update your Discord credentials:

```bash
cp config/example.env volumes/config/.env
cp config/example.settings.yaml volumes/config/settings.yml
```

3. Launch the bot:

```bash
python RSAssistant.py
```

The bot's `..all` command now audits your holdings against the watchlist and
summarizes any tickers that are missing from your accounts.

### Docker

Alternatively, build and run with Docker:

```bash
docker compose up --build
```

The compose setup also includes a `watchtower` container which checks for new
images daily and automatically updates the running `rsassistant` service.

## Default Account Nicknames

When an account has no nickname in `account_mapping.json`, RSAssistant falls
back to the pattern `"{broker} {group} {account}"`. This ensures new accounts
and orders are always logged with a deterministic identifier.

## Testing

Run unit tests with:

```bash
pytest
```

## License

This project is released under the MIT License.
