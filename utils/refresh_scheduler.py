"""Scheduling utilities for the automated ``..all`` total refresh command."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable, List
from zoneinfo import ZoneInfo

from utils.config_utils import ENABLE_MARKET_REFRESH

MARKET_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
OUT_OF_HOURS_TIMES: tuple[time, ...] = (time(8, 0), time(20, 0))
_MARKET_INTERVAL_MINUTES = 15


def _build_market_refresh_times() -> tuple[time, ...]:
    """Return ``time`` objects for 15-minute cadence during market hours."""

    moments: List[time] = []
    cursor = datetime.combine(date.today(), MARKET_OPEN)
    end = datetime.combine(date.today(), MARKET_CLOSE)
    while cursor < end:
        moments.append(cursor.time())
        cursor += timedelta(minutes=_MARKET_INTERVAL_MINUTES)
    return tuple(moments)


MARKET_REFRESH_TIMES = _build_market_refresh_times()


def daily_schedule(
    day: date, market_refresh_enabled: bool | None = None
) -> List[datetime]:
    """Return scheduled run times for ``day`` in :data:`MARKET_TZ`.

    Args:
        day: Calendar day to build the schedule for.
        market_refresh_enabled: When ``True``, include the quarter-hour cadence
            used during market hours. When ``False``, only the out-of-hours
            slots are returned. Defaults to :data:`ENABLE_MARKET_REFRESH` when
            ``None``.
    """

    if market_refresh_enabled is None:
        market_refresh_enabled = ENABLE_MARKET_REFRESH

    times: List[time] = list(OUT_OF_HOURS_TIMES)
    if market_refresh_enabled and day.weekday() < 5:
        times.extend(MARKET_REFRESH_TIMES)
    return [datetime.combine(day, entry, MARKET_TZ) for entry in sorted(times)]


def iter_refresh_schedule(
    start: datetime,
    days_ahead: int = 3,
    market_refresh_enabled: bool | None = None,
) -> Iterable[datetime]:
    """Yield scheduled refresh datetimes after ``start``.

    Args:
        start: Datetime to begin searching from.
        days_ahead: Number of future days to evaluate.
        market_refresh_enabled: Forwarded to :func:`daily_schedule` to control
            whether market-hour cadence is included. Defaults to
            :data:`ENABLE_MARKET_REFRESH` when ``None``.
    """

    current = start.astimezone(MARKET_TZ)
    for offset in range(days_ahead + 1):
        target_day = (current + timedelta(days=offset)).date()
        for candidate in daily_schedule(
            target_day, market_refresh_enabled=market_refresh_enabled
        ):
            if candidate > current:
                yield candidate


def compute_next_refresh_datetime(
    now: datetime, market_refresh_enabled: bool | None = None
) -> datetime:
    """Return the next scheduled datetime strictly after ``now``.

    Args:
        now: Reference point used to determine the next run.
        market_refresh_enabled: Forwarded to :func:`iter_refresh_schedule` to
            control whether market-hour cadence is considered. Defaults to
            :data:`ENABLE_MARKET_REFRESH` when ``None``.
    """

    for candidate in iter_refresh_schedule(
        now, days_ahead=7, market_refresh_enabled=market_refresh_enabled
    ):
        return candidate
    # Fallback to a bounded delay to avoid tight loops if schedule misconfigured
    return now.astimezone(MARKET_TZ) + timedelta(minutes=_MARKET_INTERVAL_MINUTES)
