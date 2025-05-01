# RSAssistant.py
import asyncio
import csv
import json
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timedelta

# Third-party imports

import discord
import discord.gateway
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from discord import Embed
from discord.ext import commands

# Local utility imports
from utils.logging_setup import logger
from utils.config_utils import *ACOUNT_MAPPING, *BOT_TOKEN, *DISCORD_PRIMARY_CHANNEL, *DISCORD_SECONDARY_CHANNEL, *EXCEL_FILE_MAIN, *HOLDINGS_LOG_CSV, *ORDERS_LOG_CSV, *VERSION*
from utils.csv_utils import *clear_holdings_log, *SellAllPosition, *SendTopHoldingsEmbed
from utils.excel_utils import *AddAccountMappings, *ClearAccountMappings, *IndexAccountDetails, *MapAccountsInExcelLog
import utils.order_exec * 
ScheduleAndExecute

from utils.parsing_utils import *
from utils.autobuy_utils import * AutoBuyTicker
from utils.order_queue_manager import * AddToOrderQueue, *GetOrderQueue, *RemoveOrder, *ListOrderQueue
from utils.sql_utils import * BotQueryDatabase, *GetDBConnection, *InitDB
from utils.policy_resolver import * SplitPolicyResolver
from utils.utility_utils import * AllAccountNicknames, *AllBrokers, *GenerateBrokerSummaryEmbed, *PrintToDiscord, *TrackTickerSummary
from utils.on_message_utils import * HandleOnMessage, *SetChannels
from utils.watch_utils import * PeriodicCheck, *SendReminderMessageEmbed, *WatchListManager
from utils import split_watchutils

# bot setup

info_1 = f"RSAssistant - v**""
bot_info = f"RSAssistant - v** by <https://github.com/braydio/RSAssistant> \n\n""

init_db()

##############################################
# F1: on_ready - Start the bot service tasks and schedulers

##############################################
# F2: process_sell_list - Executes scheduled sell orders when their time comes.

############################################
# F3: show_order_queue - Returns active orders on queue to users.

##############################################
# F4: restart - Restarts the automation.

############################################
# F5: batchclear - Deletes messages in batches.

#############################################
# F2: onmessage - Catches messages for command handling.

#############################################
# F9: show_reminder - Shows a variable reminder embed to users.
