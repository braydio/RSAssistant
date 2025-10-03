"""Tests for the :mod:`utils.refresh_scheduler` helpers."""

from datetime import datetime

from utils.refresh_scheduler import compute_next_refresh_datetime, MARKET_TZ


def test_next_refresh_during_market_hours_defaults_to_evening_without_toggle():
    """Without the opt-in toggle, market hours fall back to the 8 PM run."""

    now = datetime(2024, 5, 6, 10, 5, tzinfo=MARKET_TZ)
    expected = datetime(2024, 5, 6, 20, 0, tzinfo=MARKET_TZ)
    assert compute_next_refresh_datetime(now) == expected


def test_next_refresh_during_market_hours_with_toggle_uses_next_quarter_hour():
    """Enabling the toggle restores the market-hour cadence."""

    now = datetime(2024, 5, 6, 10, 5, tzinfo=MARKET_TZ)
    expected = datetime(2024, 5, 6, 10, 15, tzinfo=MARKET_TZ)
    assert compute_next_refresh_datetime(now, market_refresh_enabled=True) == expected


def test_next_refresh_after_close_uses_evening_run():
    """After market close, the same day's evening run should be chosen."""

    now = datetime(2024, 5, 6, 18, 0, tzinfo=MARKET_TZ)
    expected = datetime(2024, 5, 6, 20, 0, tzinfo=MARKET_TZ)
    assert compute_next_refresh_datetime(now) == expected


def test_next_refresh_weekend_rolls_forward_to_morning():
    """Weekend mornings schedule the next 8:00 AM run."""

    now = datetime(2024, 5, 11, 9, 0, tzinfo=MARKET_TZ)  # Saturday
    expected = datetime(2024, 5, 11, 20, 0, tzinfo=MARKET_TZ)
    assert compute_next_refresh_datetime(now) == expected


def test_next_refresh_after_evening_rolls_to_next_day_morning():
    """Late-night checks should roll to the next day's 8:00 AM slot."""

    now = datetime(2024, 5, 11, 21, 0, tzinfo=MARKET_TZ)  # Saturday evening
    expected = datetime(2024, 5, 12, 8, 0, tzinfo=MARKET_TZ)
    assert compute_next_refresh_datetime(now) == expected
