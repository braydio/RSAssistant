# OrderFlowbot

## Overview

OrderFlowbot is a tracking system designed to help manage and monitor the progress of reverse-split share roundups across multiple broker accounts. The bot provides detailed account summaries, tracks stock movements, and facilitates efficient monitoring of holdings across over 30 accounts.

## Features

- **Stock Watchlist Management**:
  - Add, remove, and track stocks across multiple accounts.
  - Retrieve the status of stocks (e.g., bought, held, sold).
  
- **Broker Summary**:
  - Generate summaries for each broker with total holdings and value per account.
  - Get a summary across all holdings for each broker.
  
- **Account Management**:
  - Seamlessly update and log holdings data.
  - Track progress for stocks as they move through different accounts.

## Program Flow and Structure

To better understand the flow of the program and how functions are called or passed, refer to the following resources:

- [Program Function Flow](main/program_function_flow.md) - Detailed flow of how the program works internally.
- [Program Map](main/program_map.txt) - A hierarchical structure outlining the modules and functions in the project.

## Project Structure

The project is organized into several utility modules under the `utils/` directory, each of which has specific responsibilities. This map is so that I can have some semblance of organization, but hopefully is a good enough reference. 
.main/
    ├── 
    ├── README.md
    ├── program_map.txt
    ├── program_function_flow
    ├── .gitignore
    ├── utils 
    │   ├── config_utils.py # Configuration loading and account nickname mappings.
    │   ├── watch_utils.py # Manage the stock watchlist and tracking progress. 
    │   ├── csv_utils.py # Handle CSV file operations like saving and reading holdings data. 
    │   ├── parsing_utils.py # Parsing and sending large messages to Discord. 
    │   ├── excel_utils.py # Interact with Excel files for logging and updating stock data. 
    │   └── example_utils.py # Placeholder for additional utility functions.
    │
    ├── excel/ 
    │   │
    │   │
    │  
    ├── logs 
        ├── holdings_log.csv
        ├── orders_log.csv
        └── archive/
            ├── 
            ├── 
            └── 