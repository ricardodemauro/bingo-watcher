"""In-memory per-ticker trade counters, reset each new trading day.

Pure logic, independent of the network: the trading-day resolver is
injected so this module can be exercised without hitting Alpaca (see
market_calendar.MarketCalendar for the real, Alpaca-backed resolver).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Iterable

TradingDayResolver = Callable[[datetime], date]


class TradeCounters:
    """Cumulative trade counts per ticker for the current trading day, plus
    which tickers have already fired an alert today.

    Both are reset together when `observe_trading_day` detects that the
    trading day has changed since the last call.
    """

    def __init__(self, tickers: Iterable[str], trading_day_resolver: TradingDayResolver) -> None:
        self._trading_day_resolver = trading_day_resolver
        self._counts: dict[str, int] = {ticker: 0 for ticker in tickers}
        self._alerted: set[str] = set()
        self._trading_day: date | None = None

    @property
    def trading_day(self) -> date | None:
        return self._trading_day

    def observe_trading_day(self, now: datetime) -> bool:
        """Resolve the trading day for `now` and reset state if it has
        changed since the last observation. Returns True if a reset happened.
        """
        resolved = self._trading_day_resolver(now)
        if self._trading_day is None:
            self._trading_day = resolved
            return False
        if resolved == self._trading_day:
            return False
        self._trading_day = resolved
        self._reset()
        return True

    def _reset(self) -> None:
        for ticker in self._counts:
            self._counts[ticker] = 0
        self._alerted.clear()

    def increment(self, ticker: str) -> None:
        self._counts[ticker] = self._counts.get(ticker, 0) + 1

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)

    def mark_alerted(self, ticker: str) -> None:
        self._alerted.add(ticker)

    def has_alerted(self, ticker: str) -> bool:
        return ticker in self._alerted
