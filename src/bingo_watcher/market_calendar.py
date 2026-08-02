"""Alpaca trading-calendar lookups, used to detect trading-day rollovers
and to gate evaluation cycles to market hours.

Kept separate from stream.py: this is an occasional REST lookup against
Alpaca's trading calendar, not part of the live market-data websocket.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from alpaca.trading.models import Calendar
from alpaca.trading.requests import GetCalendarRequest

_EASTERN = ZoneInfo("America/New_York")
_LOOKBACK_DAYS = 10


class MarketCalendar:
    """Resolves trading-day/session information for a given moment.

    A trading day "starts" when that session's market open passes, and
    stays current through the close and after-hours until the next
    session's open passes - matching the cumulative-since-open counting
    in counters.py.
    """

    def __init__(self, api_key: str, secret_key: str, *, client: TradingClient | None = None) -> None:
        self._client = client or TradingClient(api_key, secret_key, paper=True)

    def current_trading_day(self, now: datetime) -> date:
        session = self._most_recently_opened_session(now.astimezone(_EASTERN))
        if session is None:
            return now.astimezone(_EASTERN).date()
        return session.date

    def is_market_open(self, now: datetime) -> bool:
        now_eastern = now.astimezone(_EASTERN)
        session = self._most_recently_opened_session(now_eastern)
        if session is None:
            return False
        return now_eastern <= session.close.replace(tzinfo=_EASTERN)

    def _most_recently_opened_session(self, now_eastern: datetime) -> Calendar | None:
        start = now_eastern.date() - timedelta(days=_LOOKBACK_DAYS)
        sessions = self._client.get_calendar(
            GetCalendarRequest(start=start, end=now_eastern.date())
        )

        opened_sessions = [
            session
            for session in sessions
            if session.open.replace(tzinfo=_EASTERN) <= now_eastern
        ]
        if not opened_sessions:
            return None

        return max(opened_sessions, key=lambda session: session.date)
