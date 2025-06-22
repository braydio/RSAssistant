RSAssistant

RSAssistant is a high-performance, fully autonomous trading assistant built on top of Discord and Python.
It automatically monitors NASDAQ reverse split notices, parses press releases and SEC filings, intelligently detects fractional share policies (specifically share round-up scenarios), and schedules orders for   [autoRSA by Nelson Dane](https://github.com/NelsonDane/autoRSA).

Note: autoRSA is required for full order execution functionality

⸻

Features
	•	Real-time monitoring of NASDAQ reverse split alerts.
	•	Smart parsing of press releases and SEC filings for fractional share policies.
	•	Intelligent round-up detection using advanced text analysis.
	•	Autobuy order execution based on confirmed round-up scenarios.
	•	Dynamic scheduling: handles market open/close, weekends, and holidays.
	•	Professional-grade logging for full traceability and debugging.
	•	Seamless Discord integration for alerts, updates, and order confirmations.
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
	1.	Clone the repository:

git clone https://github.com/your-org/RSAssistant.git
cd RSAssistant

	2.	Set up your Python environment:

'''
python -m venv .venv
source .venv/bin/activate # If on Windows run '.venv/Scripts/activate'
pip install -r requirements.txt
'''

	3.	Configure your environment variables or .env file.
	4.	Launch the bot:

python RSAssistant.py



⸻

🛡 Safety Features

Happy money printing! ✌🏻

⸻

