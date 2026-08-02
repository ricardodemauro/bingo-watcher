"""Telegram alert delivery via python-telegram-bot's Bot.send_message.

Uses the Bot class only - this app sends alerts, it never receives
updates, so no Application, updater, polling, or handlers are needed.
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Bot
from telegram.error import RetryAfter, TelegramError

from bingo_watcher.evaluator import Alert

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_INITIAL_RETRY_DELAY_SECONDS = 2.0


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, *, bot: Bot | None = None) -> None:
        self._bot = bot or Bot(bot_token)
        self._chat_id = chat_id

    async def start(self) -> None:
        """Initializes the bot's HTTP resources and validates the token."""
        await self._bot.initialize()

    async def stop(self) -> None:
        await self._bot.shutdown()

    async def send_alert(self, alert: Alert) -> None:
        """Sends an alert. Delivery failures are logged and swallowed after
        a few retries - a Telegram outage must not take down the watcher or
        lose the alert's DB record, which is already written by then.
        """
        text = (
            f"Unusual trading activity: {alert.ticker}\n"
            f"Trades today: {alert.count}\n"
            f"Watchlist median: {alert.median:.1f}\n"
            f"Threshold: {alert.threshold:.1f}\n"
            f"Time: {alert.at.isoformat()}"
        )

        delay = _INITIAL_RETRY_DELAY_SECONDS
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                await self._bot.send_message(chat_id=self._chat_id, text=text)
                return
            except RetryAfter as exc:
                retry_after = exc.retry_after
                retry_seconds = (
                    retry_after.total_seconds()
                    if hasattr(retry_after, "total_seconds")
                    else retry_after
                )
                logger.warning("Telegram rate limited, retrying in %.0fs", retry_seconds)
                await asyncio.sleep(retry_seconds)
            except TelegramError as exc:
                logger.warning(
                    "Telegram send failed (attempt %d/%d): %s", attempt, _MAX_ATTEMPTS, exc
                )
                if attempt == _MAX_ATTEMPTS:
                    logger.error(
                        "giving up on Telegram alert for %s after %d attempts",
                        alert.ticker,
                        _MAX_ATTEMPTS,
                    )
                    return
                await asyncio.sleep(delay)
                delay *= 2
