import asyncio
from datetime import date

from bingo_watcher.counters import TradeCounters
from bingo_watcher.stream import TradeStream


class FakeTrade:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol


def _counters(*tickers: str) -> TradeCounters:
    return TradeCounters(tickers, lambda now: date(2026, 8, 3))


def test_on_trade_increments_the_matching_ticker():
    counters = _counters("AAPL", "MSFT")
    stream = TradeStream("key", "secret", ["AAPL", "MSFT"], counters)

    asyncio.run(stream._on_trade(FakeTrade("AAPL")))
    asyncio.run(stream._on_trade(FakeTrade("AAPL")))
    asyncio.run(stream._on_trade(FakeTrade("MSFT")))

    assert counters.snapshot() == {"AAPL": 2, "MSFT": 1}


def test_stop_before_run_never_opens_a_connection():
    counters = _counters("AAPL")

    def factory_should_not_be_called():
        raise AssertionError("stream factory must not be called once stopped")

    stream = TradeStream(
        "key", "secret", ["AAPL"], counters, stream_factory=factory_should_not_be_called
    )

    async def scenario():
        await stream.stop()
        await asyncio.wait_for(stream.run(), timeout=2)

    asyncio.run(scenario())
