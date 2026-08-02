from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from bingo_watcher.market_calendar import MarketCalendar


def _session(day: date, open_hm: str, close_hm: str):
    session = MagicMock()
    session.date = day
    session.open = datetime.strptime(f"{day.isoformat()} {open_hm}", "%Y-%m-%d %H:%M")
    session.close = datetime.strptime(f"{day.isoformat()} {close_hm}", "%Y-%m-%d %H:%M")
    return session


def _calendar_with(*sessions):
    client = MagicMock()
    client.get_calendar.return_value = list(sessions)
    return MarketCalendar("key", "secret", client=client)


def test_during_market_hours_returns_todays_session():
    today = date(2026, 8, 3)  # a Monday
    calendar = _calendar_with(_session(today, "09:30", "16:00"))

    # 2026-08-03 14:00 UTC = 10:00 America/New_York, mid-session.
    now = datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)

    assert calendar.current_trading_day(now) == today


def test_before_first_session_open_falls_back_to_the_moment_date():
    calendar = _calendar_with()  # no sessions returned at all

    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)

    assert calendar.current_trading_day(now) == date(2026, 8, 3)


def test_after_close_still_belongs_to_that_days_session():
    today = date(2026, 8, 3)
    calendar = _calendar_with(_session(today, "09:30", "16:00"))

    # 2026-08-03 22:00 UTC = 18:00 America/New_York, after the 16:00 close.
    now = datetime(2026, 8, 3, 22, 0, tzinfo=timezone.utc)

    assert calendar.current_trading_day(now) == today


def test_before_next_open_still_belongs_to_previous_session_eg_over_a_weekend():
    friday = date(2026, 7, 31)
    monday = date(2026, 8, 3)
    calendar = _calendar_with(
        _session(friday, "09:30", "16:00"),
        _session(monday, "09:30", "16:00"),
    )

    # Saturday morning: Friday's session opened, Monday's has not yet.
    now = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)

    assert calendar.current_trading_day(now) == friday


def test_once_next_open_passes_it_becomes_current():
    friday = date(2026, 7, 31)
    monday = date(2026, 8, 3)
    calendar = _calendar_with(
        _session(friday, "09:30", "16:00"),
        _session(monday, "09:30", "16:00"),
    )

    # 2026-08-03 14:00 UTC = 10:00 America/New_York, after Monday's open.
    now = datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)

    assert calendar.current_trading_day(now) == monday


def test_is_market_open_during_session():
    today = date(2026, 8, 3)
    calendar = _calendar_with(_session(today, "09:30", "16:00"))

    now = datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)  # 10:00 ET

    assert calendar.is_market_open(now) is True


def test_is_market_open_false_before_first_session():
    calendar = _calendar_with()

    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)

    assert calendar.is_market_open(now) is False


def test_is_market_open_false_after_close():
    today = date(2026, 8, 3)
    calendar = _calendar_with(_session(today, "09:30", "16:00"))

    now = datetime(2026, 8, 3, 22, 0, tzinfo=timezone.utc)  # 18:00 ET

    assert calendar.is_market_open(now) is False


def test_is_market_open_false_over_a_weekend():
    friday = date(2026, 7, 31)
    monday = date(2026, 8, 3)
    calendar = _calendar_with(
        _session(friday, "09:30", "16:00"),
        _session(monday, "09:30", "16:00"),
    )

    now = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)  # Saturday

    assert calendar.is_market_open(now) is False
