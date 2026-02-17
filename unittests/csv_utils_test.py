import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import csv_utils


def _write_holdings_csv(path, headers, rows):
    """Write a holdings CSV fixture with explicit headers and rows."""

    with open(path, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


def test_missing_columns_fails_and_blocks_sql(tmp_path, caplog):
    csv_path = tmp_path / "holdings.csv"
    headers = [h for h in csv_utils.HOLDINGS_HEADERS if h != "Timestamp"]
    _write_holdings_csv(
        csv_path,
        headers,
        [["k1", "Broker", "1", "A1", "XYZ", 1, 2, 2, 3]],
    )

    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True

    calls = {"count": 0}

    def fake_batch(_):
        calls["count"] += 1
        return 0

    csv_utils.update_holdings_live_batch = fake_batch

    caplog.clear()
    caplog.set_level(logging.ERROR)
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

    assert calls["count"] == 0
    assert any("missing required columns" in r.message for r in caplog.records)


def test_extra_columns_fails_and_blocks_sql(tmp_path, caplog):
    csv_path = tmp_path / "holdings.csv"
    headers = csv_utils.HOLDINGS_HEADERS + ["Unexpected"]
    _write_holdings_csv(
        csv_path,
        headers,
        [
            [
                "k1",
                "Broker",
                "1",
                "A1",
                "XYZ",
                1,
                2,
                2,
                3,
                "2020-01-01 00:00:00",
                "extra",
            ]
        ],
    )

    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True

    calls = {"count": 0}

    def fake_batch(_):
        calls["count"] += 1
        return 0

    csv_utils.update_holdings_live_batch = fake_batch

    caplog.clear()
    caplog.set_level(logging.ERROR)
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

    assert calls["count"] == 0
    assert any("unexpected columns" in r.message for r in caplog.records)


def test_type_coercion_failure_blocks_sql(tmp_path, caplog):
    csv_path = tmp_path / "holdings.csv"
    _write_holdings_csv(
        csv_path,
        csv_utils.HOLDINGS_HEADERS,
        [["k1", "Broker", "1", "A1", "XYZ", "bad", 2, 2, 3, "2020-01-01 00:00:00"]],
    )

    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True

    calls = {"count": 0}

    def fake_batch(_):
        calls["count"] += 1
        return 0

    csv_utils.update_holdings_live_batch = fake_batch

    caplog.clear()
    caplog.set_level(logging.ERROR)
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

    assert calls["count"] == 0
    assert any("invalid Quantity value" in r.message for r in caplog.records)


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


def test_save_holdings_negative_quantity_skips_sql(tmp_path):
    csv_path = tmp_path / "holdings.csv"
    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True

    calls = {"count": 0}

    def fake_batch(_rows):
        calls["count"] += 1
        return 0

    csv_utils.update_holdings_live_batch = fake_batch

    csv_utils.save_holdings_to_csv(
        [
            {
                "broker": "Fennel",
                "group": "1",
                "account": "0001",
                "ticker": "EJH",
                "quantity": -1,
                "price": 2.76,
            }
        ]
    )

    assert csv_path.exists()
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["Stock"] == "EJH"
    assert float(rows[0]["Quantity"]) == -1.0
    assert calls["count"] == 0


def test_successful_ingest_writes_sql_only_for_valid_rows(tmp_path):
    csv_path = tmp_path / "holdings.csv"
    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True

    sql_calls = []

    def fake_batch(rows):
        sql_calls.append(rows)
        return len(rows)

    csv_utils.update_holdings_live_batch = fake_batch

    csv_utils.save_holdings_to_csv(
        [
            {
                "broker": "Fennel",
                "group": "1",
                "account": "0001",
                "ticker": "AMZE",
                "quantity": 1,
                "price": 1.25,
            },
            {
                "broker": "Fennel",
                "group": "1",
                "account": "0002",
                "ticker": "EJH",
                "quantity": -1,
                "price": 2.76,
            },
        ]
    )

    with open(csv_path, newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 2
    assert len(sql_calls) == 1
    assert len(sql_calls[0]) == 1
    assert sql_calls[0][0]["ticker"] == "AMZE"


def test_save_order_to_csv_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CSV_LOGGING_ENABLED", "false")
    import importlib
    import utils.config_utils as cu
    import utils.csv_utils as cu_mod

    importlib.reload(cu)
    cu_mod = importlib.reload(cu_mod)

    cu_mod.ORDERS_LOG_CSV = str(tmp_path / "orders.csv")
    cu_mod.save_order_to_csv({})
    assert not (tmp_path / "orders.csv").exists()


def test_save_holdings_to_csv_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CSV_LOGGING_ENABLED", "false")
    import importlib
    import utils.config_utils as cu
    import utils.csv_utils as cu_mod

    importlib.reload(cu)
    cu_mod = importlib.reload(cu_mod)

    cu_mod.HOLDINGS_LOG_CSV = str(tmp_path / "holdings.csv")
    cu_mod.save_holdings_to_csv(
        [
            {
                "broker": "B",
                "group": "1",
                "account": "A1",
                "ticker": "XYZ",
                "quantity": 1,
                "price": 1,
                "value": 1,
                "account_total": 1,
            }
        ]
    )
    assert not (tmp_path / "holdings.csv").exists()
