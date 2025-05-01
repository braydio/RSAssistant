# RSAssistant.py

# Standard library imports
import asyncio
import json
import logging
import os
import signal
import sys
from datetime import datetime, timedelta

# Third-party imports
import discord
from discord import Embed
import discord.ext as lext
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Local application imports
from utils.config_utils import (
    ACCOUNT_MAPPING,
    BOT_TOKEN,
    DISCORD_PRIMARY_CHANNEL,
    DISCORD_SECONDARY_CHANNEL,
    EXCEL_FILE_MAIN,
    HOLDINGS_LOG_CSV,
    VERSION,
i
rom utils.csv_utils import clear_holdings_log, remove_from_holdings_embed, sell_all_position,
from utils.excel_utils import (
    add_account_mappings,
    clear_account_mappings,
    index_account_details,
    map_accounts_in_excel_log,
)
from utils.order_exec import process_sell_list, schedule_and_execute
from utils.parsing_utils import (
    alert_channel_message,
    parse_embed_message,
    parse_order_message,
)
from utils.autobuy_utils import autobuy_ticker
from utils.order_queue_manager import (
    add_to_order_queue,
    get_order_queue,
    remove_order,
    list_order_queue,
)
from utils.sql_utils import bot_query_database, get_db_connection, init_db