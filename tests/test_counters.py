from datetime import date, datetime, timezone

from bingo_watcher.counters import TradeCounters

DAY_ONE = date(2026, 8, 3)
DAY_TWO = date(2026, 8, 4)


def _resolver_returning(day: date):
    return lambda now: day


def test_first_observation_does_not_reset():
    counters = TradeCounters(["AAPL"], _resolver_returning(DAY_ONE))
    counters.increment("AAPL")

    reset = counters.observe_trading_day(datetime.now(timezone.utc))

    assert reset is False
    assert counters.trading_day == DAY_ONE
    assert counters.snapshot() == {"AAPL": 1}


def test_increment_accumulates_per_ticker():
    counters = TradeCounters(["AAPL", "MSFT"], _resolver_returning(DAY_ONE))

    counters.increment("AAPL")
    counters.increment("AAPL")
    counters.increment("MSFT")

    assert counters.snapshot() == {"AAPL": 2, "MSFT": 1}


def test_trading_day_rollover_resets_counts_and_alerts():
    day = DAY_ONE
    counters = TradeCounters(["AAPL"], lambda now: day)
    counters.observe_trading_day(datetime.now(timezone.utc))
    counters.increment("AAPL")
    counters.mark_alerted("AAPL")

    day = DAY_TWO
    reset = counters.observe_trading_day(datetime.now(timezone.utc))

    assert reset is True
    assert counters.trading_day == DAY_TWO
    assert counters.snapshot() == {"AAPL": 0}
    assert counters.has_alerted("AAPL") is False


def test_same_trading_day_does_not_reset():
    counters = TradeCounters(["AAPL"], _resolver_returning(DAY_ONE))
    counters.observe_trading_day(datetime.now(timezone.utc))
    counters.increment("AAPL")

    reset = counters.observe_trading_day(datetime.now(timezone.utc))

    assert reset is False
    assert counters.snapshot() == {"AAPL": 1}


def test_alert_dedup_flag():
    counters = TradeCounters(["AAPL", "MSFT"], _resolver_returning(DAY_ONE))

    assert counters.has_alerted("AAPL") is False
    counters.mark_alerted("AAPL")
    assert counters.has_alerted("AAPL") is True
    assert counters.has_alerted("MSFT") is False
