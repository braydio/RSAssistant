# RSAssistant / OrderFlowbot

## Overview

RSAssistant / OrderFlowbot is a tracking system designed to run in a discord channel alongside [auto-rsa by Nelson Dane](https://github.com/NelsonDane/auto-rsa) to help manage and monitor the progress of reverse-split share roundups across multiple broker accounts. The bot provides account summaries, tracks stocks your different brokerage accounts, and hopefully makes monitoring way the heck easier.

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
   
  |>>> Start the robit as detailed in the next few lines:

```   
python -m venv venv
venv/Scripts/activate
pip install -r requirements.txt
python orderFlowbot.py discord
```
7(?) I probably missed some stuff but feel free to DM me if you have questions 

## Account Names

Account names are set in config/account_mapping.json. 
The names listed on the 
```
    LEFT SIDE     |     RIGHT SIDE
is the OUTPUT     |     ARE CUSTOM NAMES
FROM auto-rsa     |     which can be modified

          "Webull": { 
            "1234": "Margin Account Nickname",
            "2345": "Account Nickname",
            "NNO1": "IRA Nickname",
            "NNON": "Roth IRA Nickname"
```
To set your custom nicknames, change the 4 digits (eg. 1234) to the actual last 4 for each respective account.
Set the names on the right side to whatever you would like. 
>[!NOTE]
>If the names on the right side of the mapping match the names set in the excel log, the bot with update the excel log automatically.

Fennel (having not account numbers) is parsed into psuedo-account numbers with Broker Group Number + Account

- Fennel 1 Account 1 will be mapped as Fennel 11
- Fennel 2 Account 3 will be Fennel 23 
- Fennel 3 etc. 3 etc. Fennel 33 <sub>and so on in this fashion <sub>forever and ever and ever...</sub></sub>

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

## Dependencies

This project relies on [auto-rsa by Nelson Dane](main/program_function_flow.md) for key stock-related data processing and order flow management. Make sure to set up and run the auto-rsa bot as described in its repository before using RSAssistant.

For more details, visit the [auto-rsa repository](https://github.com/NelsonDane/auto-rsa/blob/main/README.md)

## Program Flow and Structure

References *(these are quite outdated)*:
- [Program Function Flow](program_function_flow) - Detailed flow of how *(some of)* the program works internally *(I might finish this)*
- [Program Map](program_map.txt) - A hierarchical structure outlining the modules and functions in the project. *(See note above ^)*


