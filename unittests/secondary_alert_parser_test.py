import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.secondary_alert_parser import alert_channel_message, analyze_press_release
from utils.on_message_utils import OnMessagePolicyResolver


def test_alert_channel_message_parses_globenewswire():
    msg = (
        "📰 | Athira Pharma Announces Reverse Stock Split\n"
        "https://www.globenewswire.com/news-release/2025/09/11/3148572/0/en/"
        "Athira-Pharma-Announces-Reverse-Stock-Split.html\n"
        "(NASDAQ: ATHA)"
    )
    result = alert_channel_message(msg)
    assert result["ticker"] == "ATHA"
    assert result["reverse_split_confirmed"]
    assert result["url"].startswith("https://www.globenewswire.com")


def test_analyze_press_release_extracts_policy_and_date(monkeypatch):
    sample_text = (
        "Athira Pharma Announces Reverse Stock Split. "
        "The reverse stock split will be effective on September 11, 2025. "
        "No fractional shares will be issued and any fractional share will be "
        "rounded up to the nearest whole share."
    )

    def fake_fetch_body_text(url):
        return sample_text

    monkeypatch.setattr(
        OnMessagePolicyResolver.resolver, "fetch_body_text", fake_fetch_body_text
    )

    info = analyze_press_release("http://example.com/press")
    assert info["effective_date"] == "2025-09-11"
    assert "rounded up" in info["policy"].lower()
