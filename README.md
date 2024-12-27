
# RSAssistant

RSAssistant is a Python-powered Discord bot designed to be run adjacent to [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa/blob/main/guides/discordBot.md). It aids in reverse-split arbitrage trades using auto-rsa, leveraging functoinality for tracking reverse splits with quick summary views for holdings and order activity. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

---

## Features

- **Discord Integration**:
  - Real-time notifications for split activity and account updates.
  - Automated periodic reminders.
  - Support for slash commands and text-based commands.

- **Reverse Split Tracking**:
  - Add, track, and remove tickers with associated split dates and ratios.
  - Advanced commands to query brokers and holdings by ticker or summary.

- **Account and Order Management**:
  - Map accounts from Excel sheets.
  - Sync and update mappings to Excel logs.
  - Query accounts and orders via SQL-based commands.

- **Web Search Integration**:
  - Search stock splits by ticker, date range, or generate weekly reports.
  - Fetch and display reverse split filings from SEC sources.

- **Logging and Alerts**:
  - Notify users of negative holdings or abnormal activity.
  - Comprehensive logging for errors, commands, and bot activity.

- **Docker Support**:
  - Deploy seamlessly using Docker for containerized environments.

---

## Commands Overview

| Command               | Description                                                                      |
|-----------------------|----------------------------------------------------------------------------------|
| `..watch`             | Add a ticker to the watchlist with split date and ratio.                        |
| `..watchlist`         | List all currently watched tickers.                                             |
| `..watched`           | Remove a ticker from the watchlist.                                             |
| `..loadmap`           | Map accounts from the Excel sheet.                                              |
| `..loadlog`           | Sync mapped accounts to the Excel log.                                          |
| `..brokerlist`        | List all active brokers, optionally filter by broker name.                      |
| `..brokerwith`        | Show broker-level summary for a specific ticker.                                |
| `..grouplist`         | Show summary of accounts by owner group.                                        |
| `..top`               | Display the top holdings by dollar value, grouped by broker.                    |
| `..rsasearch`         | Fetch reverse split filings, with optional excerpts or summaries.               |
| `..websearch`         | Search splits by ticker, date range, or generate weekly reports.                |
| `..clearholdings`     | Clear all entries in the holdings log.                                          |
| `..clearmap`          | Clear all account mappings from the configuration.                              |
| `..restart`           | Restart the bot (under development).                                            |
| `..shutdown`          | Gracefully shut down the bot.                                                   |

---

## Web Search Integration

RSAssistant integrates with web scraping utilities to fetch and display reverse stock split data. Supported modes:

1. **Search by Ticker**:
   ```bash
   ..websearch search <ticker>
   ```

2. **Weekly Report**:
   ```bash
   ..websearch report
   ```

3. **Custom Date Range**:
   ```bash
   ..websearch custom <start_date> <end_date>
   ```

---

## Configuration

### Environment Variables (`.env`)

- `BOT_TOKEN`: Discord bot token.
- `DISCORD_PRIMARY_CHANNEL`: Channel ID for main operations.
- `DISCORD_SECONDARY_CHANNEL`: Channel ID for alerts.

### YAML Configuration (`settings.yaml`)

Defines paths, logging levels, and Excel-related settings.

---

## Installation

### Prerequisites

- [auto-rsa by NelsonDane](https://github.com/NelsonDane/auto-rsa) 
- Python 3.8 or newer
- `pip` (Python package manager)
- [Docker](https://www.docker.com/) (optional, for containerized deployments)


### Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/braydio/RSAssistant.git
   cd RSAssistant
   ```

2. **Install Dependencies**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Set Up Configuration**:
   - Copy `.env.example` to `.env` and set your variables.
   - Adjust `config/settings.yaml` to suit your environment.

4. **Run the Bot**:
   ```bash
   python src/RSAssistant.py
   ```

### Docker Deployment

1. Build and run the container:
   ```bash
   docker-compose up --build -d
   ```

2. Stop the container:
   ```bash
   docker-compose down
   ```

---

## Logging and Alerts

- Log files are stored in the `volumes/` directory and persist across docker runs and CLI runs.
- Alerts and reminders are sent to the specified Discord channels.

---

## Contributing

Contributions are welcome. Please follow these steps:

1. Fork the repository.
2. Create a feature branch.
3. Write and test your changes.
4. Submit a pull request.

---

## License

This project is licensed under the [MIT License](LICENSE).

---


## Dependencies

This project relies on [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa/blob/main/guides/discordBot.md) for key stock-related data processing and order flow management
For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)
