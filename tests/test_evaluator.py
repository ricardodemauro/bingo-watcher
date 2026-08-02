import asyncio
from datetime import date, datetime, timezone

from bingo_watcher.counters import TradeCounters
from bingo_watcher.evaluator import Evaluator
from bingo_watcher.storage import Storage

TODAY = date(2026, 8, 3)


class AlwaysOpenCalendar:
    def is_market_open(self, now: datetime) -> bool:
        return True


class AlwaysClosedCalendar:
    def is_market_open(self, now: datetime) -> bool:
        return False


def _counters(counts: dict[str, int]) -> TradeCounters:
    counters = TradeCounters(counts.keys(), lambda now: TODAY)
    counters.observe_trading_day(datetime.now(timezone.utc))
    for ticker, n in counts.items():
        for _ in range(n):
            counters.increment(ticker)
    return counters


def _evaluator(counts, storage, *, calendar=None, multiplier=1.5, on_alert=None):
    alerts = []

    async def default_on_alert(alert):
        alerts.append(alert)

    evaluator = Evaluator(
        _counters(counts),
        calendar or AlwaysOpenCalendar(),
        storage,
        multiplier=multiplier,
        interval_seconds=300,
        on_alert=on_alert or default_on_alert,
    )
    return evaluator, alerts


def test_flags_tickers_above_median_times_multiplier(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, alerts = _evaluator({"AAPL": 100, "MSFT": 10, "TSLA": 20}, storage)

    asyncio.run(evaluator._run_cycle())

    # sorted counts [10, 20, 100] -> median 20, threshold 30
    assert [a.ticker for a in alerts] == ["AAPL"]
    assert alerts[0].median == 20
    assert alerts[0].threshold == 30
    assert alerts[0].count == 100


def test_alerts_once_per_day_even_if_still_above_threshold(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, alerts = _evaluator({"AAPL": 100, "MSFT": 10, "TSLA": 20}, storage)

    asyncio.run(evaluator._run_cycle())
    asyncio.run(evaluator._run_cycle())
    asyncio.run(evaluator._run_cycle())

    assert len(alerts) == 1
    assert alerts[0].ticker == "AAPL"


def test_skips_cycle_entirely_when_market_closed(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, alerts = _evaluator(
        {"AAPL": 100, "MSFT": 10}, storage, calendar=AlwaysClosedCalendar()
    )

    asyncio.run(evaluator._run_cycle())

    assert alerts == []
    count = storage._conn.execute("SELECT COUNT(*) FROM trade_count_snapshots").fetchone()[0]
    assert count == 0


def test_all_zero_counts_do_not_alert(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, alerts = _evaluator({"AAPL": 0, "MSFT": 0, "TSLA": 0}, storage)

    asyncio.run(evaluator._run_cycle())

    assert alerts == []


def test_single_trade_does_not_alert_when_rest_of_watchlist_is_idle(tmp_path):
    # median([1, 0, 0]) == 0, which would otherwise make any nonzero count
    # look "above threshold" - the zero-median guard should suppress this.
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, alerts = _evaluator({"AAPL": 1, "MSFT": 0, "TSLA": 0}, storage)

    asyncio.run(evaluator._run_cycle())

    assert alerts == []


def test_single_ticker_watchlist_never_alerts_against_its_own_median(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, alerts = _evaluator({"AAPL": 500}, storage)

    asyncio.run(evaluator._run_cycle())

    assert alerts == []


def test_even_length_watchlist_uses_averaged_median(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, alerts = _evaluator(
        {"AAPL": 100, "MSFT": 10, "TSLA": 20, "GOOG": 30}, storage
    )

    asyncio.run(evaluator._run_cycle())

    # sorted counts [10, 20, 30, 100] -> median (20+30)/2 = 25, threshold 37.5
    assert [a.ticker for a in alerts] == ["AAPL"]
    assert alerts[0].median == 25
    assert alerts[0].threshold == 37.5


def test_records_a_snapshot_row_per_ticker_each_cycle(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, _alerts = _evaluator({"AAPL": 5, "MSFT": 3}, storage)

    asyncio.run(evaluator._run_cycle())

    rows = storage._conn.execute(
        "SELECT ticker, count FROM trade_count_snapshots ORDER BY ticker"
    ).fetchall()
    assert rows == [("AAPL", 5), ("MSFT", 3)]


def test_records_alert_event_matching_dedup_lookup(tmp_path):
    storage = Storage(tmp_path / "test.sqlite3")
    evaluator, _alerts = _evaluator({"AAPL": 100, "MSFT": 10, "TSLA": 20}, storage)

    asyncio.run(evaluator._run_cycle())

    assert storage.alerted_tickers_for_day(TODAY) == {"AAPL"}
