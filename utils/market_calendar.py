"""Market calendar helpers for trading-day and market-hours checks."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from utils.config_utils import MARKET_HOLIDAYS

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)


def _coerce_market_tz(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=MARKET_TZ)
    return timestamp.astimezone(MARKET_TZ)


def is_market_holiday(day: date) -> bool:
    return day in MARKET_HOLIDAYS


def is_market_day(day: date) -> bool:
    return day.weekday() < 5 and not is_market_holiday(day)


def is_market_open_at(timestamp: datetime) -> bool:
    current = _coerce_market_tz(timestamp)
    if not is_market_day(current.date()):
        return False
    return MARKET_OPEN <= current.time() <= MARKET_CLOSE


def next_market_open(reference: datetime) -> datetime:
    """Return the next market-open timestamp at or after ``reference``."""

    current = _coerce_market_tz(reference)
    if is_market_day(current.date()):
        if current.time() <= MARKET_OPEN:
            return datetime.combine(current.date(), MARKET_OPEN, MARKET_TZ)
        if current.time() <= MARKET_CLOSE:
            return current

    next_day = current.date() + timedelta(days=1)
    while not is_market_day(next_day):
        next_day += timedelta(days=1)
    return datetime.combine(next_day, MARKET_OPEN, MARKET_TZ)
