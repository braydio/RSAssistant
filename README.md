# OrderFlowbot

-- todo
  - print headers to orders_log.csv / holdings_log.csv
  - finish Schwab, Chase parsing order confirms

## Overview

OrderFlowbot is a tracking system designed to run in the same discord channel as [auto-rsa by Nelson Dane](main/program_function_flow.md) to help manage and monitor the progress of reverse-split share roundups across multiple broker accounts. The bot provides account summaries, tracks stocks within your different brokerage accounts, and makes monitoring way the heck easier.

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

- **Watchlist Management for Active R/S Position**:
  - Add, remove specific tickers for the bot to track. This should be done *before* sending any orders for new r/s stocks.
  - To add/remove: ..watch/watched *ticker*
    
- **Bot Commands from within Discord Channel**:
  - Enter the bot commands to the same channel that the auto-rsa bot is in.
  - Command prefix is '..' so not to conflict with '!rsa' prefix
    - Eg: '..brokerwith arqq' lists all brokers with position in ARQQ
  - Can use '..help' to list all commands
  -   *all commands listed do not all work all the way yet, please enjoy responsibly* :)

**AND** *drumroll*
- **Excel Log with Automatic Updates**:
  - Currently logs for Fidelity, Webull, Fennel, Robinhood, Public, BBAE, Vanguard, working on Schwab, Chase  

## Program Flow and Structure

To (hopefully) better understand the flow of the program and how functions are called or passed, refer to the following *(slightly outdated and rather incomplete)* resources:

- [Program Function Flow](main/program_function_flow.md) - Detailed flow of how *(some of)* the program works internally *(I might finish this)*
- [Program Map](main/program_map.txt) - A hierarchical structure outlining the modules and functions in the project. *(See note above ^)*

## Dependencies

This project relies on [auto-rsa by Nelson Dane](main/program_function_flow.md) for key stock-related data processing and order flow management. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)
