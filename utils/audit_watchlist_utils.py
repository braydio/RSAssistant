import csv
import logging
import os
from typing import Dict, List, Set

from utils.config_utils import HOLDINGS_LOG_CSV
from utils.watch_utils import watch_list_manager

logger = logging.getLogger(__name__)


def _load_holdings() -> Dict[str, Dict[str, Set[str]]]:
    """Load holdings from the CSV grouped by broker and account."""
    holdings: Dict[str, Dict[str, Set[str]]] = {}
    if not os.path.exists(HOLDINGS_LOG_CSV):
        logger.warning("Holdings log not found: %s", HOLDINGS_LOG_CSV)
        return holdings

    with open(HOLDINGS_LOG_CSV, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            broker = row.get("Broker Name", "").strip()
            account = row.get("Account Number", "").strip()
            ticker = row.get("Stock", "").strip().upper()
            if not broker or not ticker:
                continue
            holdings.setdefault(broker, {}).setdefault(account, set()).add(ticker)
    return holdings


def audit_missing_tickers(target_broker: str | None = None) -> Dict[str, Dict[str, List[str]]]:
    """Return brokers missing watchlist tickers.

    Args:
        target_broker: Optional broker to limit the audit.

    Returns:
        Dict mapping broker -> {ticker: [accounts missing]}
    """
    watchlist = set(watch_list_manager.get_watch_list().keys())
    holdings = _load_holdings()
    results: Dict[str, Dict[str, List[str]]] = {}

    for broker, accounts in holdings.items():
        if target_broker and broker.lower() != target_broker.lower():
            continue
        broker_tickers: Set[str] = set()
        for acc_tickers in accounts.values():
            broker_tickers.update(acc_tickers)
        missing = watchlist - broker_tickers
        if not missing:
            continue
        broker_result: Dict[str, List[str]] = {}
        for ticker in missing:
            if target_broker:
                missing_accounts = [acc for acc, tks in accounts.items() if ticker not in tks]
                broker_result[ticker] = missing_accounts
            else:
                broker_result[ticker] = []
        results[broker] = broker_result

    return results
