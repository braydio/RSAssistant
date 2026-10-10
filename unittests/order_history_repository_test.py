import csv

import pytest

from rsassistant.persistence import orders


def _order(order_id="o1", ticker="ABC"):
    return {
        "order_id": order_id,
        "Broker Name": "Broker A",
        "Broker Number": "1",
        "Account Number": "1234",
        "Order Type": "Buy",
        "Stock": ticker,
        "Quantity": "2",
        "Price": "3.5",
        "Date": "2026-10-01",
        "Timestamp": "2026-10-01 10:00:00",
    }


def _csv_order(order_id="o1", ticker="ABC"):
    row = _order(order_id, ticker)
    row.pop("order_id")
    return row


def test_order_history_insert_query_and_export(tmp_path, monkeypatch):
    db = tmp_path / "orders.db"
    csv_path = tmp_path / "orders.csv"
    monkeypatch.setattr(orders, "ORDERS_LOG_CSV", csv_path)
    orders.insert_order_history(_order(), database=db)

    rows = orders.list_order_history(ticker="abc", broker="broker a", database=db)
    assert len(rows) == 1
    assert rows[0]["account_number"] == "1234"
    assert rows[0]["total_value"] == 7

    assert orders.export_order_history_csv(csv_path, database=db) == 1
    with csv_path.open(newline="") as stream:
        exported = list(csv.DictReader(stream))
    assert exported[0]["Stock"] == "ABC"
    assert exported[0]["Order Type"] == "buy"


def test_legacy_csv_import_is_atomic_and_once(tmp_path, monkeypatch):
    db = tmp_path / "orders.db"
    csv_path = tmp_path / "legacy.csv"
    monkeypatch.setattr(orders, "ORDERS_LOG_CSV", csv_path)
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=orders.ORDER_CSV_HEADERS)
        writer.writeheader()
        writer.writerow(_csv_order())
        writer.writerow(_csv_order(order_id="", ticker="XYZ"))

    assert len(orders.list_order_history(database=db)) == 2
    assert len(orders.list_order_history(database=db)) == 2
    assert orders.import_legacy_order_csv(csv_path, database=db) == 0


def test_malformed_legacy_csv_does_not_partially_import(tmp_path, monkeypatch):
    db = tmp_path / "orders.db"
    csv_path = tmp_path / "bad.csv"
    monkeypatch.setattr(orders, "ORDERS_LOG_CSV", csv_path)
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=orders.ORDER_CSV_HEADERS)
        writer.writeheader()
        writer.writerow(_csv_order())
        invalid = _csv_order(order_id="", ticker="XYZ")
        invalid["Quantity"] = "bad"
        writer.writerow(invalid)

    with pytest.raises(ValueError, match="row 3"):
        orders.list_order_history(database=db)
    with orders._connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM OrderHistory").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM legacy_imports").fetchone()[0] == 0
