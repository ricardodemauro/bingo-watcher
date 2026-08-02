"""Periodic cross-ticker median/threshold evaluation and alert decisioning."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from bingo_watcher.counters import TradeCounters
from bingo_watcher.market_calendar import MarketCalendar
from bingo_watcher.storage import AlertEvent, Storage, TradeCountSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Alert:
    ticker: str
    count: int
    median: float
    threshold: float
    at: datetime


AlertHandler = Callable[[Alert], Awaitable[None]]


class Evaluator:
    """Runs the median/threshold check on a fixed interval while the market
    is open, recording snapshots and alert events and handing off any
    newly-flagged alerts to `on_alert` (M7 plugs the Telegram notifier in
    here; until then it's just logged).
    """

    def __init__(
        self,
        counters: TradeCounters,
        calendar: MarketCalendar,
        storage: Storage,
        multiplier: float,
        interval_seconds: int,
        on_alert: AlertHandler,
    ) -> None:
        self._counters = counters
        self._calendar = calendar
        self._storage = storage
        self._multiplier = multiplier
        self._interval_seconds = interval_seconds
        self._on_alert = on_alert
        self._stopped = False
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """Runs one evaluation cycle immediately, then on `interval_seconds`,
        until `stop()` is called."""
        while not self._stopped:
            await self._run_cycle()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval_seconds)

    async def stop(self) -> None:
        self._stopped = True
        self._stop_event.set()

    async def _run_cycle(self) -> None:
        now = datetime.now(timezone.utc)

        if self._counters.observe_trading_day(now):
            logger.info(
                "new trading day: %s - trade counts and alert flags reset",
                self._counters.trading_day,
            )

        if not self._calendar.is_market_open(now):
            logger.debug("market closed, skipping evaluation cycle")
            return

        trading_day = self._counters.trading_day
        snapshot = self._counters.snapshot()
        median = statistics.median(snapshot.values())
        threshold = median * self._multiplier

        logger.info(
            "evaluation cycle: %d ticker(s), median=%.2f, threshold=%.2f",
            len(snapshot),
            median,
            threshold,
        )

        for ticker, count in snapshot.items():
            self._storage.record_snapshot(
                TradeCountSnapshot(
                    ticker=ticker,
                    trading_day=trading_day,
                    recorded_at=now,
                    count=count,
                )
            )

        # A median of 0 means the watchlist is essentially idle (e.g. right
        # at the open) - any single trade would otherwise look infinitely
        # above threshold. Skip alerting entirely until there's a
        # meaningful baseline to compare against.
        if median <= 0:
            return

        flagged = [
            ticker
            for ticker, count in snapshot.items()
            if count > threshold and not self._counters.has_alerted(ticker)
        ]

        for ticker in flagged:
            count = snapshot[ticker]
            self._storage.record_alert(
                AlertEvent(
                    ticker=ticker,
                    trading_day=trading_day,
                    fired_at=now,
                    count=count,
                    median=median,
                    threshold=threshold,
                )
            )
            self._counters.mark_alerted(ticker)

            logger.info(
                "ALERT: %s count=%d median=%.2f threshold=%.2f",
                ticker,
                count,
                median,
                threshold,
            )
            await self._on_alert(
                Alert(ticker=ticker, count=count, median=median, threshold=threshold, at=now)
            )
