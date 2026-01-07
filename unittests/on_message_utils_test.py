"""Tests for helper utilities in :mod:`rsassistant.bot.handlers.on_message`."""

from rsassistant.bot.handlers.on_message import (
    _format_account_label,
    _resolve_round_up_snippet,
    format_mentions,
)


def test_format_mentions_respects_enabled_flag():
    """Mentions should respect the enabled flag unless forced."""

    ids = ["123", "456"]
    assert format_mentions(ids, enabled=True) == "<@123> <@456> "
    assert format_mentions(ids, enabled=False) == ""
    assert format_mentions(ids, enabled=False, force=True) == "<@123> <@456> "
    assert format_mentions([], enabled=True) == ""


def test_resolve_round_up_snippet_prefers_existing_snippet():
    """Existing policy snippets should be trimmed but otherwise returned."""

    policy_info = {"snippet": " Fractional shares will be rounded up to the nearest whole share. "}
    result = _resolve_round_up_snippet(policy_info, max_length=80)
    assert (
        result
        == "Fractional shares will be rounded up to the nearest whole share."
    )


def test_resolve_round_up_snippet_extracts_from_body_text():
    """Body text should be scanned when no explicit snippet is provided."""

    body_text = (
        "The company confirms fractional shares will be rounded up to the nearest whole share."
    )
    policy_info = {"body_text": body_text}
    result = _resolve_round_up_snippet(policy_info, max_length=60)
    assert result == "fractional shares will be rounded up to the nearest whole"


def test_resolve_round_up_snippet_returns_none_when_absent():
    """When no round-up language exists, no snippet should be returned."""

    body_text = "Fractional shares will be settled in cash."
    assert _resolve_round_up_snippet({"body_text": body_text}, max_length=100) is None


def test_format_account_label_skips_duplicate_broker_prefix():
    """Account label generation should include the broker prefix only once."""

    assert (
        _format_account_label("Schwab", "Schwab 1 8745")
        == "Schwab 1 8745"
    )
    assert _format_account_label("Schwab", "1 8745") == "Schwab 1 8745"
