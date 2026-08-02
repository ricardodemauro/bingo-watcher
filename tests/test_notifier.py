import asyncio
from datetime import datetime, timezone

from telegram.error import NetworkError, RetryAfter

from bingo_watcher import notifier as notifier_module
from bingo_watcher.evaluator import Alert
from bingo_watcher.notifier import TelegramNotifier

ALERT = Alert(
    ticker="AAPL",
    count=100,
    median=20.0,
    threshold=30.0,
    at=datetime(2026, 8, 3, 14, 5, tzinfo=timezone.utc),
)


class FakeBot:
    def __init__(self, behaviors):
        self._behaviors = list(behaviors)
        self.sent = []

    async def send_message(self, chat_id, text):
        behavior = self._behaviors.pop(0)
        if behavior is not None:
            raise behavior
        self.sent.append((chat_id, text))


def _fast_retries(monkeypatch):
    monkeypatch.setattr(notifier_module, "_INITIAL_RETRY_DELAY_SECONDS", 0.001)


def test_sends_message_with_alert_details():
    bot = FakeBot([None])
    notifier = TelegramNotifier("token", "chat-1", bot=bot)

    asyncio.run(notifier.send_alert(ALERT))

    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == "chat-1"
    assert "AAPL" in text
    assert "100" in text
    assert "20.0" in text
    assert "30.0" in text


def test_retries_after_transient_error_then_succeeds(monkeypatch):
    _fast_retries(monkeypatch)
    bot = FakeBot([NetworkError("boom"), None])
    notifier = TelegramNotifier("token", "chat-1", bot=bot)

    asyncio.run(notifier.send_alert(ALERT))

    assert len(bot.sent) == 1


def test_gives_up_after_max_attempts_without_raising(monkeypatch):
    _fast_retries(monkeypatch)
    bot = FakeBot([NetworkError("a"), NetworkError("b"), NetworkError("c")])
    notifier = TelegramNotifier("token", "chat-1", bot=bot)

    asyncio.run(notifier.send_alert(ALERT))  # must not raise

    assert bot.sent == []


def test_respects_retry_after_delay(monkeypatch):
    bot = FakeBot([RetryAfter(0), None])
    notifier = TelegramNotifier("token", "chat-1", bot=bot)

    asyncio.run(notifier.send_alert(ALERT))

    assert len(bot.sent) == 1
