import csv
import sys
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import utility_utils


class DummyCtx:
    def __init__(self):
        self.embeds = []

    async def send(self, embed=None, **kwargs):
        self.embeds.append(embed)


HOLDING_HEADERS = [
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


def test_track_ticker_summary_uses_latest_row(tmp_path, monkeypatch):
    file_path = tmp_path / "holdings.csv"
    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HOLDING_HEADERS)
        writer.writerow([
            "Broker Nick",
            "Broker",
            "1",
            "A1",
            "XYZ",
            5,
            1,
            1,
            1,
            "2020-01-01 00:00:00",
        ])
        writer.writerow([
            "Broker Nick",
            "Broker",
            "1",
            "A1",
            "XYZ",
            0,
            1,
            1,
            1,
            "2020-01-02 00:00:00",
        ])

    monkeypatch.setattr(
        utility_utils,
        "load_account_mappings",
        lambda: {"Broker": {"1": {"A1": "Nick"}}},
    )

    ctx = DummyCtx()
    asyncio.run(
        utility_utils.track_ticker_summary(
            ctx,
            "XYZ",
            holding_logs_file=str(file_path),
        )
    )

    assert ctx.embeds
    # Expect status ❌ because latest row has quantity 0
    field_names = [field.name for field in ctx.embeds[0].fields]
    assert any("Broker ❌" == name for name in field_names)


def test_track_ticker_summary_latest_positive(tmp_path, monkeypatch):
    file_path = tmp_path / "holdings.csv"
    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HOLDING_HEADERS)
        writer.writerow([
            "Broker Nick",
            "Broker",
            "1",
            "A1",
            "XYZ",
            0,
            1,
            1,
            1,
            "2020-01-01 00:00:00",
        ])
        writer.writerow([
            "Broker Nick",
            "Broker",
            "1",
            "A1",
            "XYZ",
            10,
            1,
            1,
            1,
            "2020-01-02 00:00:00",
        ])

    monkeypatch.setattr(
        utility_utils,
        "load_account_mappings",
        lambda: {"Broker": {"1": {"A1": "Nick"}}},
    )

    ctx = DummyCtx()
    asyncio.run(
        utility_utils.track_ticker_summary(
            ctx,
            "XYZ",
            holding_logs_file=str(file_path),
        )
    )

    assert ctx.embeds
    # Expect status ✅ because latest row has quantity 10
    field_names = [field.name for field in ctx.embeds[0].fields]
    assert any("Broker ✅" == name for name in field_names)
