
# RSAssistant

RSAssistant is a Python-powered Discord bot designed to assist with stock market operations, particularly tracking reverse splits, account management, and logging activity. Built with modularity and scalability in mind, it integrates with Discord for real-time monitoring and notifications. RSAssistant is designed to work with [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa/blob/main/guides/discordBot.md), which is essential for order execution and holdings retrieval.

## Table of Contents

- [Features](#features)
- [Directory Structure](#directory-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Commands](#commands)
- [Usage](#usage)
- [Contributing](#contributing)
- [Dependencies](#dependencies)
- [License](#license)

---

## Features

- **Discord Integration**:
  - Real-time notifications for split activity and account updates.
  - Automates reminders and periodic tasks.
- **Reverse Split Tracking**:
  - Watch and unwatch tickers with custom split dates and ratios.
  - Summarize ticker activity by broker or account.
- **Account Management**:
  - Map accounts across brokers for consolidated views.
  - Maintain detailed account mapping logs in JSON or Excel formats.
- **Logging and Archiving**:
  - Maintain detailed logs for orders, holdings, and errors.
  - Automatic archiving and backup of critical data.

---

## Directory Structure

```plaintext
RSAssistant/
├── config/               # Core configuration files
│   ├── .env              # Environment variables
│   ├── settings.yaml     # Main configuration
│   ├── example.env       # Example environment variables
│   └── example-settings.yaml  # Example YAML configuration
├── deploy/               # Deployment configurations
│   ├── Dockerfile        # Docker build file
│   ├── docker-compose.yml
│   └── entrypoint.sh     # Entrypoint script
├── dev/                  # Development-specific files
│   ├── RSAssistant.py    # Main development script
│   ├── utils/            # Utility modules
│   └── volumes/          # Local development storage
├── src/                  # Production-ready code
│   ├── RSAssistant.py    # Main production script
│   ├── utils/            # Utility modules
│   └── volumes/          # Persistent storage
├── tests/                # Test cases and test resources
└── README.md             # This README file
```

---

## Installation

### Requirements

- Python 3.8 or newer
- `pip` (Python package manager)
- [Docker](https://www.docker.com/) (optional, for containerized deployments)
- [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa/blob/main/guides/discordBot.md)

### Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/braydio/RSAssistant.git
   cd RSAssistant
   ```

2. **Set Up Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scriptsctivate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r deploy/requirements.txt
   ```

4. **Configure Environment Variables**:
   Copy the example `.env` file and customize it.
   ```bash
   cp config/example.env config/.env
   ```

5. **Run the Bot**:
   ```bash
   python src/RSAssistant.py
   ```

### Docker Deployment

For containerized deployment, use Docker:
1. Build the image:
   ```bash
   docker build -t rsassistant .
   ```
2. Run the container:
   ```bash
   docker-compose up -d
   ```

---

## Configuration

### Environment Variables (`.env`)

- `DISCORD_TOKEN`: Your Discord bot token.
- `DISCORD_CHANNEL_ID`: The channel ID where the bot will operate.
- `ENVIRONMENT`: `production`

### YAML Configuration (`settings.yaml`)

- **discord**: Bot prefix and Discord intents.
- **paths**: Define file locations for logs, backups, and mappings.
- **excel_settings**: Customizable Excel log handling.

#### Example:
```yaml
discord:
  prefix: ".."
  intents:
    message_content: true
    guilds: true

paths:
  holdings_log: "volumes/logs/holdings_log.csv"
  excel_directory: "volumes/excel/"
```

---

## Commands

| Command       | Description                                                |
|---------------|------------------------------------------------------------|
| `..watch`      | Add a ticker to the watchlist with split details.          |
| `..watchlist`  | List all watched tickers.                                  |
| `..watched`    | Remove a ticker from the watchlist.                        |
| `..loadmap`    | Load account mappings from an Excel file.                  |
| `..loadlog`    | Sync account mappings to the Excel log.                    |
| `..brokerlist` | List all currently active brokers.                         |
| `..restart`    | Restart the bot process.                                   |

For a full list of commands, see the `..help` command in Discord.

---

## Usage

### Watchlist Management

- Add a ticker with a split date and ratio:
  ```bash
  ..watch <ticker> <split_date> <split_ratio>
  ```
  Example:
  ```
  ..watch EFSH 11/8 1-10
  ```

- View all watched tickers:
  ```
  ..watchlist
  ```

- Remove a ticker:
  ```
  ..watched <ticker>
  ```

### Account Management

- Map accounts:
  ```
  ..loadmap
  ```
- Sync mappings to the Excel log:
  ```
  ..loadlog
  ```

---

## Contributing

Contributions are welcome.. Please follow these steps:

1. Fork the repository.
2. Create a new feature branch.
3. Write and test your code.
4. Submit a pull request.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Dependencies

This project relies on [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa/blob/main/guides/discordBot.md) for key stock-related data processing and order flow management. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)
