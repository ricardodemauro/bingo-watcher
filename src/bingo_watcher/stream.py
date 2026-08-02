"""Alpaca websocket trade-tick stream, feeding the trade counters."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Iterable
from typing import Callable

from alpaca.data.live import StockDataStream
from alpaca.data.models import Trade

from bingo_watcher.counters import TradeCounters

logger = logging.getLogger(__name__)

_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 60.0
_BACKOFF_RESET_AFTER_SECONDS = 60.0
_VOLUME_LOG_INTERVAL_SECONDS = 60.0


class TradeStream:
    """Runs Alpaca's IEX raw-trade stream for a watchlist, incrementing
    `counters` on every trade tick received.

    The underlying client (alpaca-py's StockDataStream) already retries
    transient websocket errors internally and forever - `run()` normally
    only returns on an unrecoverable error or an explicit `stop()`. This
    wraps it with an outer exponential-backoff loop that recreates and
    resubscribes the stream whenever that happens, so a persistent outage
    doesn't hammer Alpaca's servers on every retry.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        watchlist: Iterable[str],
        counters: TradeCounters,
        *,
        stream_factory: Callable[[], StockDataStream] | None = None,
    ) -> None:
        self._watchlist = list(watchlist)
        self._counters = counters
        self._stream_factory = stream_factory or (
            lambda: StockDataStream(api_key, secret_key)
        )
        self._stream: StockDataStream | None = None
        self._stopped = False
        self._stop_event = asyncio.Event()
        self._trades_since_log = 0

    async def run(self) -> None:
        """Runs until `stop()` is called, reconnecting on drops."""
        log_task = asyncio.create_task(self._log_volume_periodically())
        try:
            await self._run_with_reconnect()
        finally:
            log_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await log_task

    async def stop(self) -> None:
        self._stopped = True
        self._stop_event.set()
        if self._stream is not None:
            await asyncio.to_thread(self._stream.stop)

    async def _run_with_reconnect(self) -> None:
        backoff = _INITIAL_BACKOFF_SECONDS
        while not self._stopped:
            self._stream = self._stream_factory()
            self._stream.subscribe_trades(self._on_trade, *self._watchlist)
            logger.info(
                "connecting to Alpaca IEX trade stream for %d ticker(s)",
                len(self._watchlist),
            )
            connected_at = time.monotonic()
            try:
                await asyncio.to_thread(self._stream.run)
            except Exception:
                logger.exception("trade stream crashed")
            finally:
                self._stream = None

            if self._stopped:
                return

            if time.monotonic() - connected_at >= _BACKOFF_RESET_AFTER_SECONDS:
                backoff = _INITIAL_BACKOFF_SECONDS

            logger.warning("trade stream disconnected, reconnecting in %.0fs", backoff)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    async def _log_volume_periodically(self) -> None:
        while True:
            await asyncio.sleep(_VOLUME_LOG_INTERVAL_SECONDS)
            logger.debug(
                "received %d trade tick(s) in the last %.0fs",
                self._trades_since_log,
                _VOLUME_LOG_INTERVAL_SECONDS,
            )
            self._trades_since_log = 0

    async def _on_trade(self, trade: Trade) -> None:
        self._trades_since_log += 1
        self._counters.increment(trade.symbol)
