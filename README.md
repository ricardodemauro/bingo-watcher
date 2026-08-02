# bingo-watcher

Watches a configurable list of stock tickers via Alpaca and sends a
Telegram alert when a ticker's trade count is unusually high compared to
the rest of the watchlist.

See [SPEC.md](./SPEC.md) for the full requirements and [PLAN.md](./PLAN.md)
for the implementation roadmap.

## Install

```bash
uv sync
```

## Run

```bash
uv run bingo-watcher
```

Setup instructions for Alpaca and Telegram credentials will be added once
the configuration layer (M2) and notifier (M7) are implemented.
