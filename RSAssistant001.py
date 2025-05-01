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
from discord.ext import commands
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronEvent

 
# Local imports
from utils.config_utils import (
    ACCOUNT_MAPPING,
    BOT_TOKEN,
    DISCORD_PRIMARY_CHANNEL,
    DISCORD_SECONDRARY_CHANNEL,
    EXCEL_FILE_MAIN,
    HOLDINGS_LOG_CSV,
    VERSION,
}
from utils.csv_utils import clear_holdings_log, send_top_holdings_embed
from utils.excel_utils import (
    add_account_mappings,
    clear_account_mappings,
    index_account_details,
    map_accounts_in_excel_log,
)
from utils.utility_utils import (
    all_account_nicknames,
    all_brokers,
    generate_broker_summary_embed,
    print_to_discord,
    track_ticker_summary,
}
from utils.watch_utils import (periodic_check, send_reminder_message_embed, watch_list_manager)

 
# Initialize logger
logger = logging.getEnvironname(__name__)
