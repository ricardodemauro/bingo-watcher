# bingo-watcher

Watches a configurable list of stock tickers via Alpaca and sends a
Telegram alert when a ticker's trade count is unusually high compared to
the rest of the watchlist.

Every 5 minutes (configurable), bingo-watcher looks at how many trades
each watched ticker has had since the market opened, finds the median
across the whole watchlist, and flags any ticker trading noticeably more
than that median. Each ticker only notifies once per trading day. No
technical indicators (RSI, MACD, etc.) are involved - see
[SPEC.md](./SPEC.md) for the full requirements and
[PLAN.md](./PLAN.md) for the implementation roadmap.

## 1. Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv sync
```

## 2. Get an Alpaca paper account and API keys

1. Sign up (or log in) at [alpaca.markets](https://alpaca.markets).
2. Go to the [paper trading dashboard](https://app.alpaca.markets/paper/dashboard/overview).
   bingo-watcher only ever uses a **paper** account - it never places
   trades, and this keeps things safe by construction.
3. In the dashboard, find the **API Keys** panel and generate a new key
   pair. Copy both the **API Key ID** and the **Secret Key** immediately -
   the secret is only shown once.
4. The default data feed on a free account is **IEX**, which is what
   bingo-watcher uses. Note that IEX only reflects trades executed on the
   IEX exchange, not the full consolidated market - see "Known
   limitations" below.

## 3. Create a Telegram bot and find your chat ID

1. In Telegram, open a chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts (choose a name and a username).
3. BotFather replies with a **bot token** that looks like
   `123456789:AAExampleTokenNotReal`. Copy it.
4. Send your new bot any message (e.g. "hi") so Telegram has a chat to
   reference - a bot can't message you until you've messaged it first.
5. In a browser, visit:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   (replace `<YOUR_BOT_TOKEN>` with the token from step 3).
6. In the JSON response, find `"chat":{"id":...}` - that number is your
   **chat ID**. If the response is empty, make sure you actually sent the
   bot a message first, then reload the URL.

## 4. Configure

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

Edit `.env` with the credentials from steps 2 and 3:

| Variable | Where it comes from |
|---|---|
| `ALPACA_API_KEY` | Alpaca paper dashboard, step 2 |
| `ALPACA_SECRET_KEY` | Alpaca paper dashboard, step 2 |
| `TELEGRAM_BOT_TOKEN` | BotFather, step 3 |
| `TELEGRAM_CHAT_ID` | `getUpdates` response, step 3 |

Edit `config.yaml`:

| Field | Meaning |
|---|---|
| `watchlist` | Tickers to watch. Case-insensitive, duplicates are collapsed automatically. |
| `multiplier` | How far above the watchlist's median trade count a ticker must be to alert (`threshold = median * multiplier`). **There is no universally correct default** - start around `1.5` and tune it after watching a few real trading days: too low and everything alerts, too high and nothing does. |
| `evaluation_interval_seconds` | How often the median/threshold check runs. Default `300` (5 minutes). |
| `log_level` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `database_path` | Where the SQLite file (trade snapshots, alert history) is written. |

Both `config.yaml` and `.env` are gitignored - they hold your personal
settings and secrets, never commit them.

## 5. Run

```bash
uv run bingo-watcher
```

It runs continuously during market hours, reconnecting automatically if
the Alpaca connection drops. Stop it with `Ctrl-C` - it shuts down
cleanly, disconnecting the stream and closing the database before
exiting.

## 6. Reading alerts

A Telegram message looks like:

```
Unusual trading activity: AAPL
Trades today: 4218
Watchlist median: 1050.0
Threshold: 1575.0
Time: 2026-08-03T14:35:00+00:00
```

This means AAPL has traded far more often today than the typical ticker
on your watchlist - worth a look. Each ticker only alerts once per
trading day, even if it stays above threshold on later checks; the alert
history is also recorded in the SQLite database (`alert_events` table)
for later review.

## Known limitations (v1)

- **IEX-only data**: the free feed only reflects trades on the IEX
  exchange, not the full consolidated market tape. Trade counts are a
  partial, directional signal, not a complete transaction count - but
  since every watched ticker has the same bias, relative comparisons
  (this ticker vs. the rest of the watchlist) still hold up.
- **No restart recovery**: if the process restarts mid-day, that day's
  trade counts reset to zero and build back up from there. They are not
  restored from the database.
- **One shared configuration**: the multiplier and evaluation interval
  apply to the whole watchlist - there's no per-ticker tuning in v1.
- **No default multiplier**: `config.example.yaml` ships with a
  placeholder value that needs tuning against real data before alerts are
  meaningful.

See [SPEC.md](./SPEC.md) section 4 for the full list.
