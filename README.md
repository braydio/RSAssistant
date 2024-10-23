# RSAssistant
TODO:
- Restrict watchlist date values to date values, otherwise the ..watchlist/..reminder commands will break if it tries to parse a non-date
# Updates:
  - Changed main script to RSAssistant.py, to start bot run `python RSAssistant.py`
  - Changed the way accounts are mapped, they now include Broker Group # & Account # Last4
    - Webull 1 xxxxNUMB will be mapped to Webull 1 {"NUMB": "Cash Account"}
  - Errors in updating excel log will me logged to error_log.txt
    - Includes order in 'manual' format, can copy/paste to manual_order_entry.txt and run ..todiscord to re-process order
  - I forget the other changes  

## Overview

RSAssistant is a tracking system designed to run in a discord channel alongside [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa) to help manage and monitor the progress of reverse-split share roundups across multiple broker accounts. The bot provides account summaries, tracks stocks your different brokerage accounts, and hopefully makes monitoring way the heck easier.

## Setup

Hopefully add more helpful setup instructions soon but for now: 

1. Copy/paste and rename any file with 'example-' prefix
2. Follow [the instructions per this guide to set up a discord bot](https://github.com/NelsonDane/auto-rsa/blob/main/guides/discordBot.md) where it can see the output from the auto-rsa script, ideally as a live feed from your auto-rsa discord bot. 
3. Create a copy of [example-settings.yaml](https://github.com/braydio/RSAssistant/blob/master/config/example-settings.yaml) and remove the prefix 'example-'
4. Save your discord channel ID, RSA bot ID, and your discord ID per per below

>[!NOTE]
>The field `ID_OF_YOUR_NEW_BOT` will be the *token* for your new bot (not actually the ID) <sup>it's okay to be confused  <sup>I am too</sup></sup>

```
# Discord ID's
discord_ids:
  channel_id: ID_OF_YOUR_DISCORD_CHANNEL
  target_bot: ID_OF_AUTO-RSA_BOT
  my_id: YOUR_DISCORD_ID

# Discord bot settings
discord:
  token: "ID_OF_YOUR_NEW_BOT"
  token: "ID_OF_YOUR_NEW_BOT"
```
Once the settings are setting'ed and the bot is ready to start doing the work of a small team of interns,

  |> Set up and initialize a venv

  |>> Install the required packages with pip install
   
  |>>> Start the robit as in the next few lines:

```   
python -m venv venv
venv/Scripts/activate
pip install -r requirements.txt
python RSAssistant.py discord
```
7(?) I probably missed some stuff but feel free to DM me if you have questions 

## Account Names

Account names are set in config/account_mapping.json.

>[!NOTE]
>If account nickname is not specified, the account is saved as '(Broker) (Group #) (Account #)' eg 'Webull 1 1234'

The names listed on the 
```
    LEFT SIDE     |     RIGHT SIDE
is the OUTPUT     |     ARE CUSTOM NAMES
FROM auto-rsa     |     which can be modified

        "Webull 1": { 
            "1234": "Margin Account Nickname",
            "2345": "Account Nickname",
            "NNO1": "IRA Nickname",
            "NNON": "Roth IRA Nickname"
            },

```
To set your custom nicknames, change the 4 digits (eg. 1234) to the actual last 4 for each respective broker / account pair.
Set the names on the right side to whatever you would like. 

>[!NOTE]
>Set your custom names to match the names set in the excel log, the bot updates the excel log automatically.


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
  - Can also send order details in bulk by saving order details down in manual_order_entry.txt in the provided format and run command '..todiscord'  

# ToDo
  - Link changes in accounts_mapping.json to excel log
  - Update excel.example for new mappings
  - Reformat account summary commands to not be such a massive text wall
  - Clean up all the non-working code from (mainly watch_utils.py)
  - Debug discord command ..brokerlist *broker* to see where this robot learned to count

## Dependencies

This project relies on [auto-rsa by Nelson Dane](main/program_function_flow.md) for key stock-related data processing and order flow management. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)

## Program Flow and Structure

References *(these are quite outdated)*:
- [Program Function Flow](program_function_flow) - Detailed flow of how *(some of)* the program works internally *(I might finish this)*
- [Program Map](program_map.txt) - A hierarchical structure outlining the modules and functions in the project. *(See note above ^)*


