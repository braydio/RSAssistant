import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import utility_utils
from rsassistant.persistence import orders as order_repository


def _sql_row(row):
    return {
        "broker": row["Broker Name"].strip(),
        "broker_number": row["Broker Number"].strip(),
        "account_number": row["Account Number"].strip(),
        "ticker": row["Stock"].strip().lstrip("$").upper(),
        "quantity": float(row["Quantity"]), "price": float(row["Price"]),
        "position_value": float(row["Quantity"]) * float(row["Price"]),
        "account_total": float(row["Account Total"]),
        "observed_at": row["Timestamp"],
    }


def test_get_order_details_uses_sql_history(tmp_path, monkeypatch):
    monkeypatch.setattr(order_repository, "DATABASE_PATH", tmp_path / "orders.db")
    monkeypatch.setattr(order_repository, "ORDERS_LOG_CSV", tmp_path / "missing.csv")
    order_repository.insert_order_history({
        "order_id": "detail-1", "Broker Name": "Fidelity", "Broker Number": "1",
        "Account Number": "12345678", "Order Type": "Sell", "Stock": "ABC",
        "Quantity": 3, "Price": 4, "Date": "2026-10-01",
        "Timestamp": "2026-10-01 10:00:00",
    })
    assert utility_utils.get_order_details("Fidelity", "5678", "abc") == (
        "Sell 3.0 ABC 2026-10-01"
    )


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
    monkeypatch.setattr(utility_utils, "get_current_holdings", lambda: [_sql_row(holdings_row)])

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


def test_track_ticker_summary_does_not_overwrite_positive_match(
    tmp_path, monkeypatch
):
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
    rows = [
        {
            "Timestamp": "2024-01-01 10:00:00",
            "Broker Name": "TestBroker",
            "Broker Number": "1",
            "Account Number": "1234",
            "Stock": "AAPL",
            "Quantity": "5",
            "Price": "10",
            "Account Total": "100",
            "Key": "TestBroker LegacyKey",
        },
        {
            "Timestamp": "2024-01-01 10:00:01",
            "Broker Name": "TestBroker",
            "Broker Number": "1",
            "Account Number": "1234",
            "Stock": "MSFT",
            "Quantity": "3",
            "Price": "20",
            "Account Total": "100",
            "Key": "TestBroker LegacyKey",
        },
    ]
    with holdings_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(utility_utils, "get_current_holdings", lambda: [_sql_row(r) for r in rows])

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
    assert timestamp == "2024-01-01 10:00:01"


def test_track_ticker_summary_normalizes_ticker_and_broker_name(tmp_path, monkeypatch):
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
        "Broker Name": " testbroker ",
        "Broker Number": " 1 ",
        "Account Number": " 1234 ",
        "Stock": " $aapl ",
        "Quantity": "5",
        "Price": "10",
        "Account Total": "100",
        "Key": "testbroker legacy",
    }
    with holdings_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(holdings_row)
    monkeypatch.setattr(utility_utils, "get_current_holdings", lambda: [_sql_row(holdings_row)])

    mapping = {"TestBroker": {"1": {"1234": "Alpha"}}}

    monkeypatch.setattr(utility_utils, "load_account_mappings", lambda: mapping)
    monkeypatch.setattr(
        utility_utils,
        "get_account_nickname",
        lambda _broker, _group, _account: "Alpha",
    )

    statuses, timestamp = asyncio.run(
        utility_utils.track_ticker_summary(
            ctx=None,
            ticker=" $AAPL ",
            collect=True,
            holding_logs_file=holdings_file,
        )
    )

    assert statuses == {"TestBroker": ("✅", 1, 1)}
    assert timestamp == "2024-01-01 10:00:00"


def test_track_ticker_summary_matches_importer_ids_to_configured_accounts(
    tmp_path, monkeypatch
):
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
    rows = [
        {
            "Timestamp": "2024-01-01 10:00:00",
            "Broker Name": "FIDELITY",
            "Broker Number": "Fidelity 1",
            "Account Number": "Z20986699",
            "Stock": "VOO",
            "Quantity": "1.037",
            "Price": "700",
            "Account Total": "750",
            "Key": "Fidelity_1_Z20986699_VOO",
        },
        {
            "Timestamp": "2024-01-01 10:00:00",
            "Broker Name": "FIDELITY",
            "Broker Number": "Fidelity 1",
            "Account Number": "250421580",
            "Stock": "VOO",
            "Quantity": "0.326",
            "Price": "700",
            "Account Total": "800",
            "Key": "Fidelity_1_250421580_VOO",
        },
    ]
    with holdings_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(utility_utils, "get_current_holdings", lambda: [_sql_row(r) for r in rows])

    mapping = {
        "Fidelity": {
            "1": {
                "6699": "Cash Account",
                "1580": "IRA",
                "80": "Legacy short ID",
            }
        }
    }
    monkeypatch.setattr(utility_utils, "load_account_mappings", lambda: mapping)

    statuses, _ = asyncio.run(
        utility_utils.track_ticker_summary(
            ctx=None,
            ticker="VOO",
            collect=True,
            holding_logs_file=holdings_file,
        )
    )

    assert statuses == {"Fidelity": ("🟡", 2, 3)}
