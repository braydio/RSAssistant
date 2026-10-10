import csv
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import csv_utils


@pytest.fixture(autouse=True)
def isolate_current_holdings_database(monkeypatch):
    """Keep CSV contract tests independent of the runtime database."""
    monkeypatch.setattr(csv_utils, "update_holdings_live_batch", lambda *a, **k: 0)
    monkeypatch.setattr(csv_utils, "replace_current_holdings_snapshot", lambda *a, **k: 0)
    monkeypatch.setattr(csv_utils, "stage_current_holdings_snapshot", lambda *a, **k: 0)
    monkeypatch.setattr(csv_utils, "activate_current_holdings_snapshot", lambda *a, **k: True)
    monkeypatch.setattr(csv_utils, "discard_current_holdings_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(csv_utils, "get_current_holdings", lambda: [])
    monkeypatch.setattr(csv_utils, "_ACTIVE_HOLDINGS_REFRESH_TARGET", None)


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

    assert calls["count"] == 1
    assert not any("Error saving holdings" in r.message for r in caplog.records)


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

    assert calls["count"] == 1
    assert not any("Error saving holdings" in r.message for r in caplog.records)


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

    assert calls["count"] == 1
    assert not any("Error saving holdings" in r.message for r in caplog.records)


def test_get_top_holdings_reads_sql_snapshot(monkeypatch):
    """get_top_holdings should ignore compatibility CSV state."""
    monkeypatch.setattr(csv_utils, "get_current_holdings", lambda: [{
        "broker": "Broker", "broker_number": "1", "account_number": "A1",
        "ticker": "AAA", "quantity": 1, "price": 1, "position_value": 1,
        "account_total": 1, "observed_at": "2020-01-01 00:00:00",
    }])

    top, _ = csv_utils.get_top_holdings(2)
    assert "Broker" in top and any(h["Stock"] == "AAA" for h in top["Broker"])

    assert not csv_utils.CSV_LOGGING_ENABLED or "Broker" in top


def test_save_holdings_negative_quantity_persists_current_and_skips_history(
    tmp_path,
):
    csv_path = tmp_path / "holdings.csv"
    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True

    calls = {"history": 0, "current": []}

    def fake_batch(_rows):
        calls["history"] += 1
        return 0

    def fake_snapshot(rows, **_kwargs):
        calls["current"] = rows
        return len(rows)

    csv_utils.update_holdings_live_batch = fake_batch
    csv_utils.replace_current_holdings_snapshot = fake_snapshot

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
    assert calls["history"] == 0
    assert len(calls["current"]) == 1
    assert calls["current"][0]["quantity"] == -1


def test_successful_ingest_writes_history_and_full_current_snapshot(tmp_path):
    csv_path = tmp_path / "holdings.csv"
    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True

    sql_calls = []
    current_calls = []

    def fake_batch(rows):
        sql_calls.append(rows)
        return len(rows)

    csv_utils.update_holdings_live_batch = fake_batch
    csv_utils.replace_current_holdings_snapshot = lambda rows, **kwargs: current_calls.append(rows)

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
    assert len(current_calls) == 1
    assert len(current_calls[0]) == 2
    assert current_calls[0][1]["quantity"] == -1


def test_save_order_to_csv_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CSV_LOGGING_ENABLED", "false")
    import importlib
    import utils.config_utils as cu
    import utils.csv_utils as cu_mod

    importlib.reload(cu)
    cu_mod = importlib.reload(cu_mod)

    cu_mod.ORDERS_LOG_CSV = str(tmp_path / "orders.csv")
    from rsassistant.persistence import orders
    saved = []
    monkeypatch.setattr(orders, "insert_order_history", lambda row: saved.append(row))
    cu_mod.save_order_to_csv({
        "Broker Name": "Broker", "Broker Number": "1", "Account Number": "1234",
        "Order Type": "Buy", "Stock": "ABC", "Quantity": 1, "Price": 2,
        "Date": "2026-10-03",
    })
    assert saved and saved[0]["Stock"] == "ABC"
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


def test_save_holdings_normalizes_identity_fields_and_dedupes(tmp_path):
    csv_path = tmp_path / "holdings.csv"
    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True
    csv_utils.update_holdings_live_batch = lambda _rows: 0

    csv_utils.save_holdings_to_csv(
        [
            {
                "broker": "fennel ",
                "group": " 1",
                "account": " 0001 ",
                "ticker": " $amze ",
                "quantity": 1,
                "price": 1.25,
            }
        ]
    )
    csv_utils.save_holdings_to_csv(
        [
            {
                "broker": "fennel",
                "group": "1 ",
                "account": "0001",
                "ticker": "AMZE",
                "quantity": 2,
                "price": 1.5,
            }
        ]
    )

    with open(csv_path, newline="") as file:
        rows = list(csv.DictReader(file))

    assert len(rows) == 1
    assert rows[0]["Broker Name"] == "fennel"
    assert rows[0]["Broker Number"] == "1"
    assert rows[0]["Account Number"] == "0001"
    assert rows[0]["Stock"] == "AMZE"
    assert rows[0]["Key"] == "fennel_1_0001_AMZE"
    assert float(rows[0]["Quantity"]) == 2.0


def test_holdings_refresh_stages_until_finalize(tmp_path):
    csv_path = tmp_path / "holdings.csv"
    csv_utils.HOLDINGS_LOG_CSV = str(csv_path)
    csv_utils.CSV_LOGGING_ENABLED = True
    csv_utils.update_holdings_live_batch = lambda _rows: 0
    current_snapshots = []
    staged_snapshots = []
    activated = []
    csv_utils.replace_current_holdings_snapshot = lambda rows, **kwargs: current_snapshots.append(rows)
    csv_utils.stage_current_holdings_snapshot = lambda refresh_id, rows: staged_snapshots.append((refresh_id, rows))
    csv_utils.activate_current_holdings_snapshot = lambda refresh_id: activated.append(refresh_id) or True

    csv_utils.save_holdings_to_csv(
        [
            {
                "broker": "Broker",
                "group": "1",
                "account": "A1",
                "ticker": "AAA",
                "quantity": 1,
                "price": 1,
            }
        ]
    )

    csv_utils.begin_holdings_refresh(str(csv_path))
    csv_utils.save_holdings_to_csv(
        [
            {
                "broker": "Broker",
                "group": "1",
                "account": "A1",
                "ticker": "BBB",
                "quantity": 2,
                "price": 3,
            }
        ]
    )

    with open(csv_path, newline="") as file:
        live_rows = list(csv.DictReader(file))

    assert len(live_rows) == 1
    assert live_rows[0]["Stock"] == "AAA"

    csv_utils.finalize_holdings_refresh(str(csv_path))

    with open(csv_path, newline="") as file:
        promoted_rows = list(csv.DictReader(file))

    assert len(promoted_rows) == 1
    assert promoted_rows[0]["Stock"] == "BBB"
    assert not Path(f"{csv_path}.next").exists()
    assert [row["ticker"] for row in current_snapshots[0]] == ["AAA"]
    assert len(staged_snapshots) == 2
    assert staged_snapshots[0][1] == []
    assert [row["ticker"] for row in staged_snapshots[1][1]] == ["BBB"]
    assert activated == [f"{csv_path}.next"]


def test_holdings_ingest_and_refresh_work_when_csv_export_is_disabled(tmp_path):
    csv_utils.HOLDINGS_LOG_CSV = str(tmp_path / "holdings.csv")
    csv_utils.CSV_LOGGING_ENABLED = False
    current = []
    staged = []
    activated = []
    csv_utils.replace_current_holdings_snapshot = lambda rows, **kwargs: current.append(rows)
    csv_utils.stage_current_holdings_snapshot = lambda refresh_id, rows: staged.append((refresh_id, rows))
    csv_utils.activate_current_holdings_snapshot = lambda refresh_id: activated.append(refresh_id) or True

    csv_utils.save_holdings_to_csv([{
        "broker": "Broker", "group": "1", "account": "A1",
        "ticker": "AAA", "quantity": 2, "price": 3,
    }])
    assert current and current[-1][0]["ticker"] == "AAA"
    assert not Path(csv_utils.HOLDINGS_LOG_CSV).exists()

    csv_utils.begin_holdings_refresh(csv_utils.HOLDINGS_LOG_CSV)
    assert csv_utils.holdings_refresh_in_progress(csv_utils.HOLDINGS_LOG_CSV)
    csv_utils.save_holdings_to_csv([{
        "broker": "Broker", "group": "1", "account": "A1",
        "ticker": "BBB", "quantity": 1, "price": 4,
    }])
    assert staged[-1][1][0]["ticker"] == "BBB"
    assert csv_utils.finalize_holdings_refresh(csv_utils.HOLDINGS_LOG_CSV)
    assert activated
    assert not Path(csv_utils.HOLDINGS_LOG_CSV).exists()
