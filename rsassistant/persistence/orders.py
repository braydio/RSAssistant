"""SQLite repository for durable order history."""

from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path
from typing import Any

from rsassistant.persistence.db import connect_runtime_db
from rsassistant.persistence.schema import run_migrations
from utils.config_utils import ORDERS_LOG_CSV, SQL_DATABASE

DATABASE_PATH = SQL_DATABASE
ORDER_CSV_HEADERS = [
    "Broker Name", "Broker Number", "Account Number", "Order Type",
    "Stock", "Quantity", "Price", "Date", "Timestamp",
]


def _connect(database=None):
    conn = connect_runtime_db(database or DATABASE_PATH)
    run_migrations(conn)
    return conn


def _normalize_order(row: dict[str, Any]) -> dict[str, Any]:
    """Accept public CSV-style or repository-style order fields."""
    def value(sql_name, csv_name, default=""):
        return row.get(sql_name, row.get(csv_name, default))

    broker_name = str(value("broker_name", "Broker Name") or "").strip()
    broker_number = str(value("broker_number", "Broker Number") or "").strip()
    account_number = str(value("account_number", "Account Number") or "").strip()
    ticker = str(value("ticker", "Stock") or "").strip().upper()
    action = str(value("action", "Order Type") or "").strip().lower()
    date = str(value("date", "Date") or "").strip()
    timestamp = str(value("timestamp", "Timestamp") or date).strip()
    try:
        quantity = float(value("quantity", "Quantity", 0))
        price = float(value("price", "Price", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Order quantity and price must be numeric") from exc
    if not all((broker_name, account_number, ticker, action, date, timestamp)):
        raise ValueError("Order is missing broker, account, ticker, action, date, or timestamp")
    if not math.isfinite(quantity) or not math.isfinite(price) or quantity < 0 or price < 0:
        raise ValueError("Order quantity and price must be finite and non-negative")
    return {
        "order_id": str(value("order_id", "order_id") or "").strip(),
        "account_id": value("account_id", "account_id") or None,
        "broker": str(value("broker", "Broker Name") or broker_name),
        "broker_name": broker_name,
        "broker_number": broker_number,
        "account_number": account_number,
        "ticker": ticker,
        "date": date,
        "action": action,
        "quantity": quantity,
        "price": price,
        "total_value": float(value("total_value", "total_value", quantity * price) or quantity * price),
        "timestamp": timestamp,
    }


def _insert(conn, order: dict[str, Any], *, ignore_duplicate=False) -> bool:
    order = _normalize_order(order)
    if not order["order_id"]:
        raise ValueError("order_id is required")
    if not order["account_id"]:
        conn.execute(
            """INSERT INTO Accounts(broker, broker_number, account_number)
               VALUES (?, ?, ?)
               ON CONFLICT(broker, broker_number, account_number) DO NOTHING""",
            (order["broker"], order["broker_number"], order["account_number"]),
        )
        row = conn.execute(
            """SELECT account_id FROM Accounts
               WHERE broker=? AND broker_number=? AND account_number=?""",
            (order["broker"], order["broker_number"], order["account_number"]),
        ).fetchone()
        order["account_id"] = int(row[0])
    verb = "INSERT OR IGNORE" if ignore_duplicate else "INSERT"
    cur = conn.execute(
        f"""{verb} INTO OrderHistory(
                order_id, account_id, broker, broker_name, broker_number,
                account_number, ticker, date, action, quantity, price,
                total_value, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        tuple(order[field] for field in (
            "order_id", "account_id", "broker", "broker_name", "broker_number",
            "account_number", "ticker", "date", "action", "quantity", "price",
            "total_value", "timestamp",
        )),
    )
    return cur.rowcount > 0


def insert_order_history(order: dict[str, Any], *, database=None) -> bool:
    """Insert an order into history, creating its account identity atomically."""
    import uuid

    normalized = dict(order)
    normalized.setdefault("order_id", str(uuid.uuid4()))
    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return _insert(conn, normalized)


def import_legacy_order_csv(path=None, *, database=None) -> int:
    """Import an existing legacy CSV once; malformed input leaves no SQL changes."""
    source = Path(path or ORDERS_LOG_CSV).expanduser()
    if not source.exists():
        return 0
    source_key = str(source.resolve())
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ORDER_CSV_HEADERS:
            raise ValueError("Legacy orders CSV has an invalid header")
        rows = list(reader)
    prepared = []
    for index, row in enumerate(rows, start=2):
        try:
            normalized = _normalize_order(row)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Legacy orders CSV row {index} is invalid: {exc}") from exc
        if not normalized["order_id"]:
            digest = hashlib.sha256(
                (source_key + "\0" + str(index) + "\0" + "\0".join(
                    str(row.get(key, "")) for key in ORDER_CSV_HEADERS
                )).encode("utf-8")
            ).hexdigest()
            normalized["order_id"] = f"legacy-csv-{digest}"
        prepared.append(normalized)

    with _connect(database) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM legacy_imports WHERE source_key=?", (source_key,)).fetchone():
            return 0
        for order in prepared:
            _insert(conn, order, ignore_duplicate=True)
        conn.execute(
            "INSERT INTO legacy_imports(source_key, imported_rows) VALUES (?, ?)",
            (source_key, len(prepared)),
        )
    return len(prepared)


def list_order_history(*, ticker=None, broker=None, limit=None, database=None):
    """Return SQL order rows newest first, importing a present legacy CSV once."""
    import_legacy_order_csv(database=database)
    sql = """SELECT order_id, broker, broker_name, broker_number, account_number,
                    ticker, date, action, quantity, price, total_value, timestamp
             FROM OrderHistory"""
    clauses, params = [], []
    if ticker:
        clauses.append("UPPER(ticker)=?")
        params.append(str(ticker).strip().upper())
    if broker:
        clauses.append("LOWER(broker_name)=?")
        params.append(str(broker).strip().lower())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date DESC, timestamp DESC, order_id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(0, int(limit)))
    with _connect(database) as conn:
        rows = conn.execute(sql, params).fetchall()
    fields = ("order_id", "broker", "broker_name", "broker_number", "account_number",
              "ticker", "date", "action", "quantity", "price", "total_value", "timestamp")
    return [dict(zip(fields, row)) for row in rows]


def export_order_history_csv(path=ORDERS_LOG_CSV, *, database=None) -> int:
    """Write a complete CSV compatibility snapshot from authoritative SQL rows."""
    rows = list_order_history(database=database)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ORDER_CSV_HEADERS)
        writer.writeheader()
        for row in reversed(rows):
            writer.writerow({
                "Broker Name": row["broker_name"], "Broker Number": row["broker_number"],
                "Account Number": row["account_number"], "Order Type": row["action"],
                "Stock": row["ticker"], "Quantity": row["quantity"], "Price": row["price"],
                "Date": row["date"], "Timestamp": row["timestamp"],
            })
    return len(rows)


__all__ = ["insert_order_history", "import_legacy_order_csv", "list_order_history", "export_order_history_csv"]
