import csv
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import csv_utils


def run_save_holdings(tmp_path, missing_column, caplog):
    file_path = tmp_path / "holdings.csv"
    headers = [
        "Key",
        "Broker Name",
        "Broker Number",
        "Account Number",
        "Stock",
        "Quantity",
        "Price",
        "Position Value",
        "Account Total",
        "Timestamp",
    ]
    headers.remove(missing_column)
    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerow(
            [
                "abc" if missing_column != "Key" else "",
                "Broker",
                "1",
                "A1",
                "XYZ",
                1,
                2,
                2,
                3,
                "2020-01-01 00:00:00" if missing_column != "Timestamp" else "",
            ]
        )

    caplog.clear()
    csv_utils.HOLDINGS_LOG_CSV = str(file_path)
    csv_utils.update_holdings_live = lambda **kwargs: None
    caplog.set_level(logging.WARNING)
    csv_utils.save_holdings_to_csv(
        [
            {
                "broker": "Broker",
                "group": "1",
                "account": "A1",
                "ticker": "XYZ",
                "quantity": 2,
                "price": 3,
            }
        ]
    )
    return [r.message for r in caplog.records]


@pytest.mark.parametrize("missing", ["Key", "Timestamp"])
def test_missing_columns_warning(tmp_path, caplog, missing):
    messages = run_save_holdings(tmp_path, missing, caplog)
    assert any("missing columns" in m for m in messages)


def test_get_top_holdings_refreshes_data(tmp_path):
    """get_top_holdings should load data from disk each call."""
    file_path = tmp_path / "holdings.csv"
    csv_utils.HOLDINGS_LOG_CSV = str(file_path)

    headers = [
        "Key",
        "Broker Name",
        "Broker Number",
        "Account Number",
        "Stock",
        "Quantity",
        "Price",
        "Position Value",
        "Account Total",
        "Timestamp",
    ]

    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerow(
            [
                "k1",
                "Broker",
                "1",
                "A1",
                "AAA",
                1,
                1,
                1,
                1,
                "2020-01-01 00:00:00",
            ]
        )

    top, _ = csv_utils.get_top_holdings(2)
    assert "Broker" in top and any(h["Stock"] == "AAA" for h in top["Broker"])

    with open(file_path, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "k2",
                "Broker",
                "1",
                "A1",
                "BBB",
                1,
                5,
                5,
                1,
                "2020-01-02 00:00:00",
            ]
        )

    top, _ = csv_utils.get_top_holdings(2)
    tickers = {h["Stock"] for h in top["Broker"]}
    assert {"AAA", "BBB"} <= tickers
