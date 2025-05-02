# RSAssistant Setup Guide

**RSAssistant** is an automated assistant built on Discord and Python, designed for real-time monitoring and handling of NASTDAQ reverse splits using information parsed from press releases and SEC filings. It executes orders based automatically and on command ([autoRSA by NelsonDane](https://github.com/NelsonDane/autoRSA) is a required dependency for order execution and logging)

---

## Features

* Reverse Split Alerts: Parses press releases and filings for actionable triggers.

* Auto Buy/Sell: Executes orders on a schedule or when splits match criteria.

* Discord Bot: Interactive command-based interface for managing tickers.

* Dynamic Scheduling: Supports market open/close, weekends, holidays.

* Database Tracking: SQL-based persistent store for holdings and orders.

* Docker-Ready: Easily runs in a containerized environment using Docker.

---

## Requirements

* Python 3.9+
* pipenv or python virtualenv recommended
* Discord bot token and channel IDs

---

## Environment Setup

1. **Clone the repo**

```bash
git clone https://github.com/braydio/RSAssistant.git
cd RSAssistant
```

2. \*\*Create ****`.env`**** in \*\***`/config/`** (or copy from `example.env`):

```dotenv
BOT_TOKEN=your_token_here
DISCORD_PRIMARY_CHANNEL=channel_with_autoRSA_active
DISCORD_SECONDARY_CHANNEL=channel_id_with_rss_feeds
ENV=production
LOG_LEVEL=INFO
LOG_FILE=volumes/logs/rsassistant.log
HEARTBEAT_ENABLED=true
HEARTBEAT_PATH=volumes/logs/heartbeat.txt
HEARTBEAT_INTERVAL=60
```

3. **Install dependencies**

```bash
pip install -r requirements.txt
```

4. **Run the bot**

```bash
python RSAssistant.py
```

---

## Configuration Files

| File                   | Purpose                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------- |
| `.env`                 | Core runtime config (bot, logging)                                                          |
| `account_mapping.json` | Maps brokers/accounts to nicknames (can be set up in excel file and mapped with `..addmap`) |
| `watch_list.json`      | Tickers to watch and conditions                                                             |
| `ReverseSplitLog.xlsx` | Master file for all account logs                                                            |
| `holdings_log.csv`     | Output: current holdings                                                                    |
| `orders_log.csv`       | Output: order history                                                                       |

---

## First-Time Run Steps

1. Add your token and channel IDs to `.env`
2. Ensure you have Excel and JSON files in place (copy from `/config/example.*`)
3. Run:

```bash
python RSAssistant.py
```

Then in Discord, use commands like:

```bash
..watch AAPL 11/4 1-10
..watchlist
..watched AAPL
..ord buy AAPL fidelity 100 10:00
..liquidate fidelity
```

---

## Resources

* [RSAssistant GitHub](https://github.com/braydio/RSAssistant)
* [autoRSA](https://github.com/NelsonDane/autoRSA)
