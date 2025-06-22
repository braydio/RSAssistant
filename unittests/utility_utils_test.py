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
