"""Alpaca trading-calendar lookups, used to detect trading-day rollovers.

Kept separate from stream.py: this is an occasional REST lookup against
Alpaca's trading calendar, not part of the live market-data websocket.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest

_EASTERN = ZoneInfo("America/New_York")
_LOOKBACK_DAYS = 10


class MarketCalendar:
    """Resolves which trading-day session a given moment belongs to.

    A trading day "starts" when that session's market open passes, and
    stays current through the close and after-hours until the next
    session's open passes - matching the cumulative-since-open counting
    in counters.py.
    """

    def __init__(self, api_key: str, secret_key: str, *, client: TradingClient | None = None) -> None:
        self._client = client or TradingClient(api_key, secret_key, paper=True)

    def current_trading_day(self, now: datetime) -> date:
        now_eastern = now.astimezone(_EASTERN)
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
            return now_eastern.date()

        return max(opened_sessions, key=lambda session: session.date).date
