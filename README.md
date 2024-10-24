# RSAssistant

TODO:
- Restrict watchlist date values to date values, otherwise the ..watchlist/..reminder commands will break if it tries to parse a non-date
 
## Overview

RSAssistant is a tracking system designed to run in a discord channel alongside [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa) to help manage and monitor the progress of reverse-split share roundups across multiple broker accounts. This script reads the output from auto-rsa in the discord channel and saves order activity and holdings information locally for quick recall / reference. Current features include a dynamic watchlist for users to specify upcoming r/s, accounts mapped to custom nicknames with order activity saved to a local excel file. This script does not directly access any of your accounts, so no credentials are needed other than discord bot / channel information.

## Setup

1. Rename files with the 'example-' prefix by removing the prefix (e.g., example-settings.yaml to settings.yaml).
2. Follow [the instructions per this guide to set up a discord bot](https://github.com/NelsonDane/auto-rsa/blob/main/guides/discordBot.md) where it can see the output from the auto-rsa script.
3. Create a copy of [example-settings.yaml](https://github.com/braydio/RSAssistant/blob/master/config/example-settings.yaml) and remove the prefix 'example-'
4. Save your discord channel ID, auto-rsa bot ID, and your discord ID per per below along with the token of your new RSAssistant bot
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
Once the settings are set, initialize the bot with the following commands: 
```   
python -m venv venv
venv/Scripts/activate
pip install -r requirements.txt
python RSAssistant.py discord
```

## Account Names

Account names are managed in two files:

  - logs/excel/ReverseSplitLog.xlsx (Excel file)
  - config/account_mapping.json (JSON file)

>[!NOTE]
>If account nickname is not specified, the account is saved as '(Broker) (Group #) (Account #)' eg 'Webull 1 1234'

 - Accounts can be defined in the shaded columns (A:E) on the Account Details sheet in ReverseSplitLog.xlsx. 
    ```
    - (Discord Account Format) |   (Excel Account Details Format)    
    -      Webull 1 xxx4565    |  (Webull) (1) (4565) (Cash Account) 
    ```
To update mappings from the excel log run `..updatemappings`
Use the provided example-account_mapping.json to avoid duplicate account mappings. The .json file does not need to be configured if you use the excel process with the ..update commands, this will be done automatically. 

Account Mapping in account_mapping.json:
```
        "Webull 1": { 
            "1234": "Margin Account Nickname",
            "2345": "Account Nickname",
            "NNO1": "IRA Nickname",
            "NNON": "Roth IRA Nickname"
            },

```

## Features

- **Watchlist Management for Active R/S Positions**:
  - Add, remove specific tickers for the bot to track. This should be done *before* sending any orders for new r/s stocks.
  -  `..watch ticker` starts watching a ticker  |  `..watched ticker` to stop watching
    
- **Other Bot Commands from within Discord Channel**:
  - Enter the bot commands to the same channel that the auto-rsa bot is in.
  - Command prefix is `..`
    - Eg: *`..brokerwith arqq`* lists all brokers with position in ARQQ
  - List all commands with *`..help`*

- **Excel Log with Automatic Updates**:
  - Currently logs for Fidelity, Webull, Fennel, Robinhood, Public, BBAE, Vanguard, Schwab, Chase, Tradier, Firstrade and any of the other ones in auto-rsa that I might be forgetting.
  - Map account names in Account Details sheet of the Excel log and run the `..updatemapping` and `..updatelog` commands and it will begin logging
  - Can also send order details in bulk by saving order details down in manual_order_entry.txt in the provided format and run command '..todiscord'  

# ToDo
  - Clean account summary command prints
  - Clean up all the non-working code from (mainly watch_utils.py)
  - Debug discord command ..brokerlist *broker* to see where this robot learned to count

## Dependencies

This project relies on [auto-rsa by Nelson Dane](main/program_function_flow.md) for key stock-related data processing and order flow management. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)

## Program Flow and Structure
wip

