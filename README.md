# OrderFlowbot

## Overview

OrderFlowbot is a tracking system designed to run in the same discord channel as [auto-rsa by Nelson Dane](main/program_function_flow.md) to help manage and monitor the progress of reverse-split share roundups across multiple broker accounts. The bot provides detailed account summaries, tracks stock movements, and makes monitoring way the heck easier.

## Features

- **Watchlist Management for Active R/S Position**:
  - Add, remove specific tickers for the bot to track.
  - Retrieve the status of each ticker being watch (e.g., not purchased, not in Y, sold / completed) *Currently bit of a WIP but mostly works*
    
- **Broker Summary**:
  - Generate summaries for each broker with total holdings / total rs holdings / account values.
  - Get a summary across all holdings for each broker.
  *Somehow I broke this today, hoping to get a fix in soon.*

**AND** *drumroll*
- **Excel Log with Automatic Updates**:
  - Seamlessly (not really, it is currently full of seams) update and log holdings data.
  - Track progress for stocks as they move through different accounts *(This also just broke lol)*
  

## Program Flow and Structure

To (hopefully) better understand the flow of the program and how functions are called or passed, refer to the following *(slightly outdated and rather incomplete)* resources:

- [Program Function Flow](main/program_function_flow.md) - Detailed flow of how *(some of)* the program works internally *(I might finish this)*
- [Program Map](main/program_map.txt) - A hierarchical structure outlining the modules and functions in the project. *(See note above ^)*

## Dependencies

This project relies on [auto-rsa by Nelson Dane](main/program_function_flow.md) for key stock-related data processing and order flow management. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)
