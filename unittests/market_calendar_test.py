"""Exchange-calendar behavior for scheduling boundaries."""

from datetime import date, datetime

from utils.market_calendar import (
    MARKET_TZ,
    is_market_open_at,
    next_market_open,
    session_close,
)


def test_nyse_calendar_accounts_for_early_close():
    close = session_close(date(2025, 11, 28))
    assert close == datetime(2025, 11, 28, 13, 0, tzinfo=MARKET_TZ)
    assert not is_market_open_at(datetime(2025, 11, 28, 14, 0, tzinfo=MARKET_TZ))


def test_next_market_open_skips_exchange_holiday():
    reference = datetime(2025, 7, 3, 17, 0, tzinfo=MARKET_TZ)
    assert next_market_open(reference) == datetime(
        2025, 7, 7, 9, 30, tzinfo=MARKET_TZ
    )
