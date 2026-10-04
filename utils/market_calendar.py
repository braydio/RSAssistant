"""NYSE session helpers backed by the exchange-calendars dataset."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

from utils.config_utils import MARKET_HOLIDAYS

MARKET_TZ = ZoneInfo("America/New_York")
_NYSE = xcals.get_calendar("XNYS", start="1990-01-01", end="2050-12-31")


def _coerce_market_tz(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=MARKET_TZ)
    return timestamp.astimezone(MARKET_TZ)


def _label(day: date) -> pd.Timestamp:
    return pd.Timestamp(day.isoformat())


def _session_for(day: date):
    if day in MARKET_HOLIDAYS:
        return None
    label = _label(day)
    sessions = _NYSE.schedule.index
    if label < sessions[0] or label > sessions[-1]:
        raise ValueError(f"NYSE calendar does not cover {day.isoformat()}.")
    # Use the schedule index directly. This also avoids exchange-calendars'
    # older nanosecond bounds path when newer pandas uses microsecond dates.
    if label not in sessions:
        return None
    return label


def is_market_holiday(day: date) -> bool:
    return _session_for(day) is None


def is_market_day(day: date) -> bool:
    return _session_for(day) is not None


def session_open(day: date) -> datetime | None:
    label = _session_for(day)
    if label is None:
        return None
    value = _NYSE.schedule.loc[label, "open"]
    return value.to_pydatetime().astimezone(MARKET_TZ)


def session_close(day: date) -> datetime | None:
    label = _session_for(day)
    if label is None:
        return None
    value = _NYSE.schedule.loc[label, "close"]
    return value.to_pydatetime().astimezone(MARKET_TZ)


def is_market_open_at(timestamp: datetime) -> bool:
    current = _coerce_market_tz(timestamp)
    opened = session_open(current.date())
    closed = session_close(current.date())
    return opened is not None and opened <= current < closed


def next_market_open(reference: datetime) -> datetime:
    """Return the next session open at or after ``reference``."""
    current = _coerce_market_tz(reference)
    day = current.date()
    while True:
        opened = session_open(day)
        closed = session_close(day)
        if opened is not None:
            if current <= opened:
                return opened
            if current < closed:
                return current
        day += timedelta(days=1)


def normalize_execution_time(timestamp: datetime) -> datetime:
    """Move an out-of-session execution to the next open, preserving valid times."""
    current = _coerce_market_tz(timestamp)
    if is_market_open_at(current):
        return current
    return next_market_open(current)
