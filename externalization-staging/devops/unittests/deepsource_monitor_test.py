import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deepsource_monitor as dm


def test_check_run_state_is_failure():
    failing = dm.CheckRunState(
        run_id=1, status="completed", conclusion="failure", html_url=None
    )
    assert failing.is_failure

    success = dm.CheckRunState(
        run_id=2, status="completed", conclusion="success", html_url=None
    )
    assert not success.is_failure

    pending = dm.CheckRunState(run_id=3, status="queued", conclusion=None, html_url=None)
    assert not pending.is_failure


def test_should_notify_changes():
    previous = dm.MonitorSnapshot(commit_sha="abcdef0", check_run=None)
    current_same = dm.MonitorSnapshot(commit_sha="abcdef0", check_run=None)
    assert not dm.should_notify(previous, current_same)

    new_commit = dm.MonitorSnapshot(commit_sha="1234567", check_run=None)
    assert dm.should_notify(previous, new_commit)

    previous_run = dm.MonitorSnapshot(
        commit_sha="abcdef0",
        check_run=dm.CheckRunState(1, "queued", None, None),
    )
    completed_run = dm.MonitorSnapshot(
        commit_sha="abcdef0",
        check_run=dm.CheckRunState(1, "completed", "success", None),
    )
    assert dm.should_notify(previous_run, completed_run)


def test_format_status_message_includes_context():
    snapshot = dm.MonitorSnapshot(commit_sha="abcdef012345", check_run=None)
    assert "abcdef0" in dm.format_status_message(snapshot)

    run = dm.CheckRunState(
        run_id=99,
        status="completed",
        conclusion="failure",
        html_url="https://example.com/check",
    )
    snapshot = dm.MonitorSnapshot(commit_sha="1234567890", check_run=run)
    message = dm.format_status_message(snapshot)
    assert "failure" in message
    assert "1234567" in message
    assert "https://example.com/check" in message


def test_fetch_deepsource_check_run(monkeypatch):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "check_runs": [
                    {
                        "id": 2,
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "https://example.com/failure",
                        "app": {"name": dm.DEEPSOURCE_APP_NAME},
                    }
                ]
            }

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(dm.requests, "get", fake_get)

    result = dm.fetch_deepsource_check_run("abc123")
    assert result is not None
    assert result.run_id == 2
    assert captured["url"].endswith("/commits/abc123/check-runs")
    assert "Authorization" in captured["headers"] or dm.GITHUB_TOKEN == ""


def test_fetch_default_branch(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"default_branch": "main"}

    monkeypatch.setattr(dm.requests, "get", lambda *a, **k: FakeResp())
    assert dm.fetch_default_branch() == "main"


def test_fetch_latest_commit_sha(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"sha": "abcdef123"}

    monkeypatch.setattr(dm.requests, "get", lambda *a, **k: FakeResp())
    assert dm.fetch_latest_commit_sha("main") == "abcdef123"
