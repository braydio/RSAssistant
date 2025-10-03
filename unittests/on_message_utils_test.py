"""Tests for helper utilities in :mod:`utils.on_message_utils`."""

from utils.on_message_utils import format_mentions


def test_format_mentions_respects_enabled_flag():
    """Mentions should respect the enabled flag unless forced."""

    ids = ["123", "456"]
    assert format_mentions(ids, enabled=True) == "<@123> <@456> "
    assert format_mentions(ids, enabled=False) == ""
    assert format_mentions(ids, enabled=False, force=True) == "<@123> <@456> "
    assert format_mentions([], enabled=True) == ""
