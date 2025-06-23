RSAssistant

RSAssistant is an autonomous trading assistant built with Python and Discord. It
tracks corporate actions from NASDAQ and the SEC, parses press releases for
fractional share policies, and schedules orders for
[autoRSA by Nelson Dane](https://github.com/NelsonDane/autoRSA) when a round-up
scenario is detected.

Note: autoRSA is required for full order execution functionality.

⸻

Features
	•	Real-time monitoring of NASDAQ reverse split alerts.
	•	Smart parsing of press releases and SEC filings for fractional share policies.
	•	Intelligent round-up detection using advanced text analysis.
	•	Autobuy order execution based on confirmed round-up scenarios.
	•	Dynamic scheduling: handles market open/close, weekends, and holidays.
	•	Professional-grade logging for full traceability and debugging.
	•	Seamless Discord integration for alerts, updates, and order confirmations.
        •       Summarize holdings by broker and owner via `..grouplist` command.
        •       Aggregated owner holdings across brokers via `..ownersummary` command.

⸻

System Architecture
	•	Bot Framework: discord.py
	•	Scheduler: Async-based delayed execution system
	•	Parser Utilities: BeautifulSoup4, Regex parsing
	•	Logging: Custom logging setup to file and console
	•	Database: SQLite3 for local persistent storage

External Sources:
	•	NASDAQ Trader News Feed
	•	SEC.gov filings
	•	NASDAQ Press Releases

⸻

Key Files

Ok, there’s a ton of junk in here to clean up… but it works. I'll get to it.

⸻

Quick Start
        1. Clone the repository:

```bash
git clone https://github.com/your-org/RSAssistant.git
cd RSAssistant
```

        2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

        3. Copy the example configuration files and edit them:

```bash
cp config/example.env config/.env
cp config/example.settings.yaml config/settings.yml
```
Fill in your Discord bot token and channel IDs inside `config/.env`.

        4. Launch the bot:

```bash
python RSAssistant.py
```

   Or run with Docker:

```bash
docker compose up --build
```



⸻

🛡 Safety Features

Happy money printing! ✌🏻

⸻

