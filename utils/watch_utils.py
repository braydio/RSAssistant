import asyncio
import csv
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta

import discord
import pandas as pd

from utils.config_utils import (DISCORD_SECONDARY_CHANNEL, SELL_FILE,
                                WATCH_FILE, load_account_mappings, load_config)
from utils.excel_utils import add_stock_to_excel_log
from utils.utility_utils import get_last_stock_price
from utils.sql_utils import update_historical_holdings

# Load configuration and paths from settings
config = load_config()
account_mapping = load_account_mappings()
