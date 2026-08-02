"""SQLite persistence for trade-count snapshots and alert events.

This store is for history and inspection only. It is not used to recover
in-memory counters after a restart (see SPEC.md section 4).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import TracebackType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_count_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    trading_day TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    count INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_ticker_day
    ON trade_count_snapshots (ticker, trading_day);

CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    trading_day TEXT NOT NULL,
    fired_at TEXT NOT NULL,
    count INTEGER NOT NULL,
    median REAL NOT NULL,
    threshold REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_ticker_day
    ON alert_events (ticker, trading_day);
"""


@dataclass(frozen=True)
class TradeCountSnapshot:
    ticker: str
    trading_day: date
    recorded_at: datetime
    count: int


@dataclass(frozen=True)
class AlertEvent:
    ticker: str
    trading_day: date
    fired_at: datetime
    count: int
    median: float
    threshold: float


class Storage:
    """SQLite-backed storage. Creates its schema on first use."""

    def __init__(self, db_path: Path) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def record_snapshot(self, snapshot: TradeCountSnapshot) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO trade_count_snapshots
                    (ticker, trading_day, recorded_at, count)
                VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot.ticker,
                    snapshot.trading_day.isoformat(),
                    snapshot.recorded_at.isoformat(),
                    snapshot.count,
                ),
            )

    def record_alert(self, event: AlertEvent) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO alert_events
                    (ticker, trading_day, fired_at, count, median, threshold)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.ticker,
                    event.trading_day.isoformat(),
                    event.fired_at.isoformat(),
                    event.count,
                    event.median,
                    event.threshold,
                ),
            )

    def alerted_tickers_for_day(self, trading_day: date) -> set[str]:
        """Tickers that already have an alert event recorded for `trading_day`.

        Used for the once-per-day alert dedup rule (SPEC.md section 3.4).
        """
        cursor = self._conn.execute(
            "SELECT DISTINCT ticker FROM alert_events WHERE trading_day = ?",
            (trading_day.isoformat(),),
        )
        return {row[0] for row in cursor.fetchall()}

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
