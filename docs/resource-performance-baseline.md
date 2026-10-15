# Resource Performance Baseline

Reproducible procedure for measuring RSAssistant's runtime footprint (TP-20261010-001).
No numbers below have been measured yet; leave cells blank until a real run fills them.
Do not quote savings without a before/after pair from the same machine and workload.

## Enabling telemetry

Telemetry is off by default and adds no task when disabled.

```env
RESOURCE_METRICS_ENABLED=true
RESOURCE_METRICS_INTERVAL_SECONDS=300
```

Each interval the bot logs one line (no tickers, accounts, URLs or message text):

```text
resource_metrics cpu_s=12.40 rss_kib=145320 loop_drift_ms=1.8 tasks=14 calls=[holdings_import=3/0.42s yfinance_batch=2/1.90s]
```

- `cpu_s`: cumulative process CPU time (`time.process_time()`); diff two lines for a rate.
- `rss_kib`: from `/proc/self/status`; `unavailable` when not on Linux (never `0`).
- `loop_drift_ms`: lateness of a 50 ms sleep, a proxy for event-loop blocking.
- `tasks`: `len(asyncio.all_tasks())`.
- `calls`: `name=count/total_seconds` for the fixed names `holdings_import`,
  `policy_resolution`, `yfinance_batch` (anything else folds into `other`).

## Scenarios

Run each with a clean `volumes/logs`, mocked network (no live broker, Discord, SEC,
LLM or yfinance traffic), and the same host. Use a short interval (e.g. 30 s) for runs.

1. **Idle, 30 minutes** — bot connected, no commands, `ENABLE_MARKET_REFRESH=false`.
2. **Market refresh simulation** — `ENABLE_MARKET_REFRESH=true` with `..all` and the
   holdings importer pointed at a fixture file; network mocked.
3. **Ticker workloads** — price fetch for 10 and for 100 tickers (mocked `yf.download`).
4. **Startup** — process start to `on_ready`.
5. **Shutdown** — SIGTERM to process exit.
6. **24-hour retained logs** — total bytes under `volumes/logs` after 24 h idle.

## Record

Per scenario: p50/p95 `loop_drift_ms`, CPU seconds, RSS (start/end), request counts
(`calls`), files written, and disk bytes before/after (`du -sb volumes/`).

| Scenario | p50 drift ms | p95 drift ms | CPU s | RSS KiB | Calls | Files written | Disk bytes Δ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Idle 30 min | | | | | | | |
| Market refresh sim | | | | | | | |
| 10 tickers | | | | | | | |
| 100 tickers | | | | | | | |
| Startup | | | | | | | |
| Shutdown | | | | | | | |
| 24 h retained logs | | | | | | | |
