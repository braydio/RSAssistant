import asyncio
import csv
import json
import logging
import os
logging.basicConfig(format='ls')
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import discord
import yaml
import yfinance as yf

from utils.config_utils import (ACCOUNT_MAPPING, 
                                HOLDINGS_LOG_CSV, ORDERS_LOG_CSV,
                                get_account_nickname, load_account_mappings,
                                load_config)

# Load configuration and holdings data
config = load_config()

# Restored function: get_last_stock_price
def get_last_stock_price(stock):
    """Fetches the last price of a given stock using Yahoo Finance."""
    try:
        ticker = yf.Ticker(stock)
        stock_info = ticker.history(period="1d")
        if not stock_info.empty:
            return round(stock_info["Close"].iloc[-1], 2)
        logging.warning(f"No stock data found for {stock}.")
        return None
    except Exception as e:
        logging.error(fError fetching last price for {stock}.: {e}")
        return None
