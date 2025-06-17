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
