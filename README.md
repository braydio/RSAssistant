# RSAssistant / OrderFlowbot

-- todo
  - print headers to orders_log.csv / holdings_log.csv

## Overview

RSAssistant / OrderFlowbot is a tracking system designed to run in a discord channel alongside as [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa) to help manage and monitor the progress of reverse-split share roundups across multiple broker accounts. The bot provides account summaries, tracks stocks your different brokerage accounts, and hopefully makes monitoring way the heck easier.

## Setup

Hopefully add more helpful setup instructions soon but for now: 

1. Copy/paste and rename any file with 'example-' prefix
2. Create a copy of [example-settings.yaml](https://github.com/braydio/RSAssistant/blob/master/config/example-settings.yaml) and remove the prefix 'example-'
3. The only changes you will need to make here are to the 4 settings below:

```
# Discord ID's
discord_ids:
  channel_id: ID_OF_YOUR_DISCORD_CHANNEL
  target_bot: ID_OF_AUTO-RSA_BOT
  my_id: YOUR_DISCORD_ID

# Discord bot settings
discord:
  token: "ID_OF_YOUR_NEW_BOT"
```
 - Change the 3 discord_ids to your discord channel ID, your auto-rsa bot discord ID, your discord ID. Your discord bot token needs to be in quotes.

4. Once the settings are setting'ed and the bot is ready to start doing the work of a small team of interns:   
   `python -m venv venv`   
   `venv/Scripts/activate`   
   `pip install -r requirements.txt`   
   and THEN
   start the robit with:   
   `python orderFlowbot.py discord`   
5. I probably missed some stuff so DM me if you have questions 


## Features

- **Watchlist Management for Active R/S Positions**:
  - Add, remove specific tickers for the bot to track. This should be done *before* sending any orders for new r/s stocks.
  -  `..watch ticker` starts watching a ticker  |  `..watched ticker` to stop watching
    
- **Bot Commands from within Discord Channel**:
  - Enter the bot commands to the same channel that the auto-rsa bot is in.
  - Command prefix is `..`
    - Eg: *`..brokerwith arqq`* lists all brokers with position in ARQQ
  - List all commands with *`..help`*
  -   *all commands listed do not all work all the way yet, please enjoy responsibly* :)

- **Excel Log with Automatic Updates**:
  - Currently logs for Fidelity, Webull, Fennel, Robinhood, Public, BBAE, Vanguard, Schwab, Chase.
  - Setup instructions per excel file  

## Dependencies

This project relies on [auto-rsa by Nelson Dane](main/program_function_flow.md) for key stock-related data processing and order flow management. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)

## Program Flow and Structure

References *(these are quite outdated)*:
- [Program Function Flow](main/program_function_flow.md) - Detailed flow of how *(some of)* the program works internally *(I might finish this)*
- [Program Map](main/program_map.txt) - A hierarchical structure outlining the modules and functions in the project. *(See note above ^)*


