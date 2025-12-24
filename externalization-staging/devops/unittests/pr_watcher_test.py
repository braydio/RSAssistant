import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pr_watcher


def test_should_restart():
    last = datetime(2024, 1, 1, tzinfo=timezone.utc)
    latest = datetime(2024, 1, 2, tzinfo=timezone.utc)
    assert pr_watcher.should_restart(last, latest)
    assert not pr_watcher.should_restart(latest, last)
    assert not pr_watcher.should_restart(None, latest)


def test_fetch_latest_merge_time(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"merged_at": "2024-01-01T00:00:00Z"}]

    monkeypatch.setattr(pr_watcher.requests, "get", lambda *a, **k: FakeResp())
    assert pr_watcher.fetch_latest_merge_time() == datetime(2024, 1, 1, tzinfo=timezone.utc)
