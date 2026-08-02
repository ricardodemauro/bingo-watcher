# bingo-watcher — Project Spec (v1)

## 1. Business Overview

bingo-watcher is a personal market-monitoring tool. It connects to a stock
brokerage account and keeps an eye on a list of stock tickers chosen by the
user. Instead of watching price charts or technical indicators, it watches
**how often a stock is being traded** — the number of buy/sell transactions
happening on it.

The idea: a sudden, unusually high number of trades on a stock (compared to
the other stocks being watched) can be a signal that something notable is
happening — news, a big move, unusual interest — worth a human's attention.
When that happens, the tool sends a notification so the user finds out
without having to sit and watch a screen all day.

### Business Goals

- Watch a user-defined list of tickers throughout the trading day.
- Continuously count how many trades occur per ticker since the market
  opened.
- Compare tickers against each other to find which ones are trading
  unusually often relative to the rest of the watchlist.
- Notify the user by Telegram the moment a ticker crosses that "unusually
  active" line — once per ticker per day, so the user isn't spammed with
  repeat alerts for the same event.
- Keep a record of activity and alerts so the day's data isn't just lost
  when the tool is closed.

### Out of Scope for v1

- No technical indicators (RSI, MACD, moving averages, etc.) — explicitly
  excluded from this version.
- No trade execution — this is a watcher/notifier only, it never places
  orders.
- No recovery of trade counts if the tool restarts mid-day — counts simply
  start over from zero for the rest of that day. Acceptable for v1.
- No per-ticker custom rules — one shared setting applies to the whole
  watchlist.
- No support for multiple notification channels beyond Telegram.

## 2. How It Should Work (Business Language)

1. The user maintains a simple list of tickers they care about, along with
   a couple of settings (see Configuration below).
2. Every trading day, for every ticker on the list, the tool keeps a running
   count of how many trades have happened since the market opened.
3. Every 5 minutes, the tool looks at all the tickers on the list together
   and finds the "typical" (median) trade count among them.
4. Any ticker trading noticeably more than that typical amount — by a
   configurable margin — is considered unusually active.
5. The first time a ticker crosses that line on a given day, the user gets
   a Telegram message about it. That ticker won't notify again for the rest
   of the day, even if it stays above the line.
6. The next trading day, everything resets and the process starts fresh.

## 3. Technical Decisions

These are the decisions already settled through requirements discussion.
Implementation architecture, file/module layout, language tooling, and
testing strategy are deliberately not covered here — those come later.

### 3.1 Broker & Market Data

- **Broker**: Alpaca.
- **Account type**: Paper trading account (not live/funded).
- **Data feed**: Free IEX feed (Alpaca's free tier). This feed only reflects
  trades executed on the IEX exchange, not the full consolidated market
  tape — trade counts are a partial, directional signal rather than a
  complete transaction count. This bias is consistent across all watched
  tickers, so relative comparisons (this ticker vs. the rest of the
  watchlist) remain meaningful even though absolute counts understate real
  market activity.

### 3.2 Data Access Method

- **Connection type**: Persistent WebSocket connection to Alpaca's
  streaming data API (not REST polling).
- **Subscription**: Raw trade tick channel, subscribed for every ticker on
  the watchlist. Each individual trade message received increments that
  ticker's counter.
- **Reconnection**: The connection should recover from drops and resume
  receiving trade ticks without manual intervention.

### 3.3 Metric Tracked

- **Metric**: Trade count (number of executed transactions), **not** share
  volume.
- **Buy/sell handling**: Buys and sells are combined into a single total
  count per ticker — not tracked separately in v1.
- **Accumulation window**: Cumulative since market open, reset at the start
  of each new trading day.

### 3.4 Alerting Logic

- **Comparison basis**: Cross-ticker median — at each evaluation, the
  median trade count is computed across all tickers currently on the
  watchlist.
- **Threshold**: `median × multiplier`. The multiplier is a configuration
  value (not hardcoded), so it can be tuned without code changes. No fixed
  default has been chosen yet — this is a config knob to be set/tuned once
  the tool is running.
- **Evaluation frequency**: Every 5 minutes during the trading day.
- **Notification dedup**: A ticker notifies at most once per trading day —
  on the first check where it crosses above the threshold. It will not
  notify again that day even if it remains above threshold on later
  checks. The dedup state resets at the start of the next trading day.

### 3.5 Notifications

- **Channel**: Telegram, via a bot posting to a chat/channel.
- Requires a Telegram bot token and a target chat ID, both supplied via
  configuration.

### 3.6 Data Persistence

- **Storage**: SQLite.
- **What's stored**: Periodic trade-count snapshots per ticker and a
  record of every alert that was fired (ticker, timestamp, count, median,
  threshold at the time).
- **Not used for**: Restart recovery in v1 — persistence here is for
  record-keeping/history, not for resuming an in-progress day's counts
  after a crash or restart.

### 3.7 Configuration

- A config file (format to be decided at scaffolding time — YAML/JSON/.env)
  will hold:
  - The list of watched tickers.
  - The alert multiplier.
  - Alpaca API credentials (paper account).
  - Telegram bot token and chat ID.
- v1 applies the same multiplier/settings to every ticker on the list —
  no per-ticker overrides.

### 3.8 Setup Requirements

- The user will need an Alpaca paper trading account with API keys, and a
  Telegram bot (with its token and target chat ID). Setup guidance for
  both will be documented separately as part of the project's README.

## 4. Known Limitations (v1)

- Trade counts reflect IEX-only activity, not the full consolidated market.
- No restart recovery — a crash or redeploy mid-day resets that ticker's
  count to zero for the remainder of the day.
- One shared alert configuration for the whole watchlist; no per-ticker
  tuning.
- Alert multiplier has no default yet — must be set in configuration
  before meaningful alerts can fire.
