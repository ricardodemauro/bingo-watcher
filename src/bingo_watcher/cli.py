"""CLI entrypoint."""

import asyncio
import contextlib
import logging
import signal
import sys

from telegram.error import TelegramError

from bingo_watcher.config import ConfigError, Settings, load_settings
from bingo_watcher.counters import TradeCounters
from bingo_watcher.evaluator import Evaluator
from bingo_watcher.logging_setup import configure_logging
from bingo_watcher.market_calendar import MarketCalendar
from bingo_watcher.notifier import TelegramNotifier
from bingo_watcher.storage import Storage
from bingo_watcher.stream import TradeStream

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()

    try:
        settings = load_settings()
    except ConfigError as exc:
        logger.error(str(exc))
        sys.exit(1)

    configure_logging(settings.log_level)
    logger.info("starting bingo-watcher")
    logger.info(
        "loaded config: %d ticker(s) watched, multiplier=%s",
        len(settings.watchlist),
        settings.multiplier,
    )

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_run(settings))

    logger.info("bingo-watcher stopped")


async def _run(settings: Settings) -> None:
    with Storage(settings.database_path) as storage:
        logger.info("database ready at %s", settings.database_path)

        calendar = MarketCalendar(settings.alpaca_api_key, settings.alpaca_secret_key)
        counters = TradeCounters(settings.watchlist, calendar.current_trading_day)
        notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)

        try:
            await notifier.start()
        except TelegramError as exc:
            logger.error("could not connect to Telegram: %s", exc)
            sys.exit(1)

        stream = TradeStream(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            settings.watchlist,
            counters,
        )
        evaluator = Evaluator(
            counters,
            calendar,
            storage,
            settings.multiplier,
            settings.evaluation_interval_seconds,
            notifier.send_alert,
        )

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

        stream_task = asyncio.create_task(stream.run())
        evaluator_task = asyncio.create_task(evaluator.run())

        await stop_event.wait()
        logger.info("shutdown signal received, stopping")

        await stream.stop()
        await evaluator.stop()
        results = await asyncio.gather(stream_task, evaluator_task, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error("component did not shut down cleanly", exc_info=result)

        await notifier.stop()


if __name__ == "__main__":
    main()
