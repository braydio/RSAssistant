import asyncio
import csv
import sys
from pathlib import Path

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


def test_track_ticker_summary_marks_broker_with_position(tmp_path, monkeypatch):
    holdings_file = tmp_path / "holdings.csv"
    fieldnames = [
        "Timestamp",
        "Broker Name",
        "Broker Number",
        "Account Number",
        "Stock",
        "Quantity",
        "Price",
        "Account Total",
        "Key",
    ]
    holdings_row = {
        "Timestamp": "2024-01-01 10:00:00",
        "Broker Name": "TestBroker",
        "Broker Number": "1",
        "Account Number": "1234",
        "Stock": "AAPL",
        "Quantity": "5",
        "Price": "10",
        "Account Total": "100",
        "Key": "TestBroker LegacyKey",
    }
    with holdings_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(holdings_row)

    mapping = {"TestBroker": {"1": {"1234": "Alpha"}}}

    def fake_load_account_mappings():
        return mapping

    def fake_get_account_nickname(broker_name, broker_number, account_number):
        broker_key = broker_name
        group_key = str(broker_number)
        account_key = str(account_number)
        return (
            mapping.setdefault(broker_key, {})
            .setdefault(group_key, {})
            .setdefault(account_key, "Alpha")
        )

    monkeypatch.setattr(
        utility_utils, "load_account_mappings", fake_load_account_mappings
    )
    monkeypatch.setattr(
        utility_utils, "get_account_nickname", fake_get_account_nickname
    )

    statuses, timestamp = asyncio.run(
        utility_utils.track_ticker_summary(
            ctx=None,
            ticker="AAPL",
            collect=True,
            holding_logs_file=holdings_file,
        )
    )

    assert statuses == {"TestBroker": ("✅", 1, 1)}
    assert timestamp == "2024-01-01 10:00:00"
