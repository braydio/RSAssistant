"""Tests for helpers in :mod:`utils.utility_utils`."""

import asyncio
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import utility_utils

def test_aggregate_owner_totals(monkeypatch):
    sample = {
        "Broker1": {"OwnerA": 100.0, "OwnerB": 50.0},
        "Broker2": {"OwnerA": 25.0, "OwnerB": 25.0, "OwnerC": 10.0},
    }
    monkeypatch.setattr(
        utility_utils,
        "all_brokers_summary_by_owner",
        lambda specific_broker=None: sample,
    )

    totals = utility_utils.aggregate_owner_totals()
    assert totals == {"OwnerA": 125.0, "OwnerB": 75.0, "OwnerC": 10.0}


def test_track_ticker_summary_multiple_ticker_refresh(tmp_path, monkeypatch):
    """Multiple tickers for one account should not hide earlier holdings."""

    csv_path = tmp_path / "holdings.csv"
    fieldnames = [
        "Timestamp",
        "Broker Name",
        "Key",
        "Stock",
        "Quantity",
        "Price",
        "Account Total",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "Timestamp": "2024-01-01 09:30:00",
                "Broker Name": "BrokerA",
                "Key": "BrokerA Alpha",
                "Stock": "AAA",
                "Quantity": "10",
                "Price": "5",
                "Account Total": "100",
            }
        )
        writer.writerow(
            {
                "Timestamp": "2024-01-01 09:30:00",
                "Broker Name": "BrokerA",
                "Key": "BrokerA Alpha",
                "Stock": "BBB",
                "Quantity": "5",
                "Price": "15",
                "Account Total": "150",
            }
        )
        writer.writerow(
            {
                "Timestamp": "2024-01-01 09:30:00",
                "Broker Name": "BrokerA",
                "Key": "BrokerA Beta",
                "Stock": "CCC",
                "Quantity": "2",
                "Price": "8",
                "Account Total": "80",
            }
        )

    account_mapping = {
        "BrokerA": {
            "Group1": {
                "00000001": "Alpha",
                "00000002": "Beta",
            }
        }
    }

    monkeypatch.setattr(utility_utils, "load_account_mappings", lambda: account_mapping)

    captured_holdings = {}
    original_compute = utility_utils.compute_broker_statuses

    def spy_compute(holdings, account_mapping):
        captured_holdings.clear()
        for broker, accounts in holdings.items():
            captured_holdings[broker] = dict(accounts)
        return original_compute(holdings, account_mapping)

    monkeypatch.setattr(utility_utils, "compute_broker_statuses", spy_compute)

    statuses, timestamp_str = asyncio.run(
        utility_utils.track_ticker_summary(
            ctx=None,
            ticker="AAA",
            collect=True,
            holding_logs_file=csv_path,
        )
    )

    assert timestamp_str == "2024-01-01 09:30:00"
    broker_status = statuses["BrokerA"]
    assert broker_status[0] == "🟡"
    assert broker_status[1] == 1
    assert broker_status[2] == 2

    broker_holdings = captured_holdings.get("BrokerA", {})
    assert "BrokerA Alpha" in broker_holdings
    assert "BrokerA Beta" not in broker_holdings
