RSAssistant

RSAssistant is a high-performance, fully autonomous trading assistant built on top of Discord and Python.
It automatically monitors NASDAQ reverse split notices, parses press releases and SEC filings, intelligently detects fractional share policies (especially round-up scenarios), and triggers smart autobuy orders.

Note: RSAssistant is designed to run in tandem with the autoRSA GitHub repository. It is required for full order execution functionality.

⸻

Features
	•	Real-time monitoring of NASDAQ reverse split alerts.
	•	Smart parsing of press releases and SEC filings for fractional share policies.
	•	Intelligent round-up detection using advanced text analysis.
	•	Autobuy order execution based on confirmed round-up scenarios.
	•	Dynamic scheduling: handles market open/close, weekends, and holidays.
	•	Professional-grade logging for full traceability and debugging.
	•	Seamless Discord integration for alerts, updates, and order confirmations.

⸻

System Architecture
	•	Bot Framework: Discord.py
	•	Scheduler: Async-based delayed execution system
	•	Parser Utilities: BeautifulSoup4, Regex parsing
	•	Logging: Custom logging setup to file and console
	•	Database: SQLite3 for local persistent storage
	•	External Sources:
	•	NASDAQ Trader News Feed
	•	SEC.gov filings
	•	NASDAQ Press Releases

⸻

Key Files

(There’s a ton of junk in here to clean up but it works.)

⸻

Quick Start
	1.	Clone the repository:

git clone https://github.com/your_org/RSAssistant.git

	2.	Set up your Python environment:

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

	3.	Configure your environment variables or .env file.
	4.	Launch the bot:

python RSAssistant.py

⸻

🛡 Safety Features

happy money printing ✌️

⸻