import asyncio
import csv
import json
import os
shutil
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
from utils.config_utils import (ACCOUNT_MAPPING, ...)
from utils.csv_utils import (clear_holdings_log, ...)
from utils.excel_utils import (...)
from utils.order_exec import (process_sell_list, ...)
from utils.parsing_utils import (alert_channel_message, ...)
from utils.autobuy_utils import autobuy_ticker
from utils.order_queue_manager import (add_to_order_queue, ...)
from utils.sql_utils import bot_query_database
from utils.policy_resolver import SplitPolicyResolver
from utils.utility_utils import (all_brokers, ...)
from utils.onmessage_utils import handle_on_message
from utils.watch_utils import (periodic_check, send_reminder_message_embed, watch_list_manager)
from utils import split_watchutils
# from utils.Webdriver_Scraper import StockSplitScraper