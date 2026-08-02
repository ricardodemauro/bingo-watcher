# bingo-watcher — Implementation Plan

Sequential milestone plan for building v1 as specified in [SPEC.md](./SPEC.md).

**How to use this document**: milestones are strictly ordered — each one
builds on the previous and assumes it is complete and merged. Work is
delegated one milestone per session; a session should read `SPEC.md` and
this file, implement exactly one milestone, verify it, and commit. Do not
pull scope forward from later milestones.

## Pre-Settled Technical Decisions

These apply across all milestones. They are decided — implement against
them rather than re-litigating them mid-milestone.

| Area | Decision |
|---|---|
| Language | Python 3.11+ |
| Runtime model | Single long-running `asyncio` process, launched from a CLI |
| Packaging / deps | `uv` with `pyproject.toml` |
| Broker SDK | `alpaca-py` (official SDK — provides the async `StockDataStream`) |
| Market data | Alpaca **paper** account, **IEX** feed, **raw trade tick** stream |
| Config | YAML file for settings + `.env` for secrets, loaded via `pydantic-settings` |
| Storage | SQLite via the stdlib `sqlite3` module (writes are infrequent — every 5 min — so a sync driver is acceptable) |
| Telegram | Direct HTTPS calls to the Bot API via `httpx` (no bot framework — the app only *sends*) |
| Secrets | Never committed. `.env` is gitignored; `.env.example` is committed |

**Verification approach**: each milestone lists a concrete "Done when"
check. Automated tests are not a milestone requirement in v1 — but where a
milestone's logic is pure and easy to exercise (M4, M5), a small test is
encouraged rather than manual poking.

---

## M1 — Project Scaffolding

**Goal**: An installable, runnable, empty-but-wired Python project.

**Scope**
- `pyproject.toml` with project metadata and the dependency set above.
- Package directory (e.g. `bingo_watcher/`) with module placeholders that
  match the milestones ahead: `config.py`, `storage.py`, `stream.py`,
  `counters.py`, `evaluator.py`, `notifier.py`, `cli.py`.
- CLI entrypoint registered as a console script (e.g. `bingo-watcher`) that
  currently just starts, logs "starting", and exits cleanly.
- Logging set up once, centrally (level configurable, timestamps on).
- README stub describing what the project is and how to install it.

**Done when**: `uv sync` installs cleanly and running the CLI prints a
startup log line and exits with status 0.

---

## M2 — Configuration Layer

**Goal**: All runtime settings load from files, validated, with clear
errors on bad input.

**Scope**
- YAML config holding: watchlist tickers, alert multiplier, evaluation
  interval (default 5 minutes), log level.
- `.env` holding: Alpaca API key/secret, Telegram bot token, Telegram chat
  ID.
- Typed settings model that merges both sources and validates:
  - watchlist is non-empty, tickers are uppercased/deduplicated
  - multiplier is a positive number
  - all four secrets are present
- Commit `config.example.yaml` and `.env.example`; gitignore the real ones.
- Fail fast at startup with a readable message naming the missing/invalid
  field — never a raw traceback for a config mistake.

**Note**: the alert multiplier has **no chosen default** (see SPEC §3.4).
Ship `config.example.yaml` with a placeholder value and a comment saying it
needs tuning against live data.

**Done when**: the CLI loads a valid config and logs the ticker count and
multiplier; a config missing a required field exits non-zero with a clear
message.

---

## M3 — SQLite Storage Layer

**Goal**: A persistence layer ready for the app to write into.

**Scope**
- Schema creation on startup (idempotent — safe to run every launch).
- Two tables:
  - **trade count snapshots**: ticker, trading day, timestamp, cumulative
    count at that moment.
  - **alert events**: ticker, trading day, timestamp, the ticker's count,
    the median across the watchlist, and the threshold in force when it
    fired.
- Write helpers for both, plus a read helper for "alerts already fired
  today" (used later by M6's dedup, and useful for inspection).
- Database file path comes from config, with a sensible default.

**Reminder**: per SPEC §3.6 this store is for history and inspection only.
It is explicitly **not** used to restore counters after a restart in v1 —
do not build recovery logic here.

**Done when**: launching the app creates the DB file with both tables, and
a manual insert/read round-trip through the helpers works.

---

## M4 — Trade Counters & Trading-Day State

**Goal**: The in-memory counting model, independent of the network.

**Scope**
- An in-memory structure holding a cumulative trade count per ticker for
  the current trading day.
- An increment operation (called once per trade tick in M5).
- Trading-day awareness: determine the current trading day and detect when
  a new one starts, using Alpaca's clock/calendar rather than naive
  wall-clock date math (handles holidays and half-days correctly).
- On a new trading day: reset all counters to zero **and** clear the
  per-ticker "already alerted today" flags.
- A snapshot read that returns the current counts for all watched tickers.

**Done when**: counters increment correctly, a simulated trading-day
rollover zeroes both the counts and the alert flags, and the snapshot
reflects live state. This milestone is pure logic — worth a small unit
test rather than manual verification.

---

## M5 — Alpaca WebSocket Trade Stream

**Goal**: Live trade ticks flowing from Alpaca into the M4 counters.

**Scope**
- Connect `StockDataStream` against the **IEX** feed using paper-account
  credentials.
- Subscribe to the **raw trade** channel for every ticker in the watchlist.
- On each trade message, increment that ticker's counter (M4).
- Reconnect on drop with exponential backoff, re-subscribing on reconnect,
  logging each disconnect/reconnect.
- Do **not** backfill missed trades on reconnect — per SPEC §1, counts are
  allowed to under-report after an interruption in v1.
- Log received-trade volume periodically at debug level so it's visible
  that data is actually arriving.

**Done when**: run during market hours against a live IEX feed and observe
counters climbing for actively-traded tickers. Outside market hours, verify
the connection establishes and subscribes without error (no ticks will
arrive — that's expected, and worth logging clearly so it doesn't look
like a failure).

---

## M6 — Median Evaluation & Alert Decisioning

**Goal**: The core business rule — decide *when* something is worth
alerting about. Does not send anything yet.

**Scope**
- A periodic task on the configured interval (default 5 minutes).
- Each cycle:
  1. Snapshot current counts for all watched tickers (M4).
  2. Compute the **median count across the watchlist**.
  3. Threshold = `median × multiplier`.
  4. Flag every ticker whose count exceeds the threshold.
  5. Drop any ticker that already alerted today (dedup — SPEC §3.4).
  6. Write a snapshot row per ticker, and an alert-event row per surviving
     flagged ticker (M3).
  7. Mark those tickers as alerted for the day.
- Emit the surviving alerts to a handler seam that M7 plugs the notifier
  into — for this milestone, log them.
- Only evaluate while the market is open; skip cycles when it's closed.

**Edge cases to handle explicitly**: an all-zero watchlist (median 0 —
every nonzero ticker would otherwise trip the threshold; require a nonzero
count to alert), a single-ticker watchlist, and even-length watchlists
where the median falls between two values.

**Done when**: with counters seeded to known values, each cycle logs the
correct median, threshold, and flagged set — and a ticker that stays above
threshold logs an alert exactly once, not on every cycle.

---

## M7 — Telegram Notifier & Full Wiring

**Goal**: The complete app — alerts actually reach the user's phone.

**Scope**
- Send a Telegram message via the Bot API for each alert produced by M6.
- Message content: ticker, its trade count, the watchlist median, the
  threshold, and the time — enough to act on without opening the app.
- Delivery failures are logged and swallowed, never fatal: a Telegram
  outage must not take down the watcher or lose the alert's DB record.
  Retry a small number of times with backoff before giving up.
- Wire the full pipeline in the CLI: config → storage → counters →
  stream → evaluator → notifier, running the stream and the evaluation
  loop concurrently under `asyncio`.
- Graceful shutdown on Ctrl-C / SIGTERM: stop the stream, finish any
  in-flight write, close the DB.

**Done when**: the app runs end-to-end during market hours and a real
Telegram message arrives for a flagged ticker; Ctrl-C shuts it down
cleanly with no traceback.

---

## M8 — Setup Documentation

**Goal**: Someone starting from an empty machine can run this.

**Scope**
- README covering: what the tool does, install steps, how to run it, and
  how to read the alerts it sends.
- Step-by-step for obtaining an **Alpaca paper trading account** and its
  API key/secret.
- Step-by-step for creating a **Telegram bot** (BotFather) and finding the
  target **chat ID**.
- A documented walkthrough of every config field, including guidance that
  the multiplier needs tuning against real observed data.
- A short "known limitations" section restating SPEC §4 — especially that
  IEX-only data under-reports true market activity, and that a mid-day
  restart resets counts.

**Done when**: the README can be followed start-to-finish on a clean
checkout to a working, alerting instance.

---

## Deliberately Deferred (Not in This Plan)

Restart/count recovery, per-ticker rule overrides, buy/sell split, extra
notification channels, technical indicators (RSI/MACD), and any
order-placing capability. All are out of scope for v1 per SPEC §1 — if one
becomes desirable, it's a v2 conversation, not a mid-milestone addition.
