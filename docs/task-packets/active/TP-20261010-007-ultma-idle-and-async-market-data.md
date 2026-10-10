# TP-20261010-007: ULT-MA Plugin Nonblocking Market Data and Idle Efficiency

**Packet ID:** TP-20261010-007  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-007-ultma-idle-and-async-market-data.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** Normal  
**Authoring chat:** not-recorded  

## Objective

Reduce ult-ma plugin nonblocking market data and idle efficiency overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `plugins/ultma/ult_ma_bot.py`
- `plugins/ultma/market_data.py`
- `plugins/ultma/cog.py`
- `plugins/ultma/unittests/trading_ult_ma_bot_test.py`
- `plugins/ultma/unittests/trading_market_data_test.py`
- `config/.env.example`

## Confirmed current behavior

`UltMaTradingBot._monitor_loop()` and `_position_loop()` call synchronous yfinance methods within async task paths: `_determine_color`, `_check_position`, and `force_entry`; `YFinanceMarketDataProvider.fetch_candles()` retries with `time.sleep`. Optional plugin is loaded only when `ENABLED_PLUGINS=ultma`.

## Required changes and implementation order

1. Offload synchronous market-data acquisition via `await asyncio.to_thread` at `_refresh_color()`, `_check_position()`, and `force_entry()` boundaries; keep Discord/trade orchestration on the event loop. Use one per-plugin semaphore to prevent overlapping identical polling cycles, with cancellation-safe cleanup.
2. Cache the same TQQQ candle-series only within its effective candle interval when requested repeatedly; do not cache position exit prices beyond the existing configured `TRADING_PRICE_CHECK_INTERVAL_SECONDS`, and never serve stale data for a stop-loss solely to save requests.
3. When no active position exists, `_position_loop` should cheaply skip fetch and retain its existing interval. Monitor loop may use schedule-aligned bounded sleeps where behavior equivalent. Do not skip premarket/extended-hours checks if the configuration permits that mode.
4. Ensure the network provider's `time.sleep` executes in a worker only. Add precise retry ceilings and error counters without full payload logging. Verify task cancellation when cog unloads and pause mode.
5. Keep `ENABLE_AUTOMATED_TRADING` default false and existing order decision/risk controls unchanged.

## Focused tests and validation

Use fake provider to simulate 2-second blocking fetch and validate event-loop probe remains responsive, no duplicate fetch in same candle, position exit uses an adequately fresh quote, pause/unload cancel tasks, and disabled plugin starts no polling. `python -m pytest -q plugins/ultma/unittests`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] ULT-MA market-data fetches do not stall Discord; monitoring remains behavior-equivalent and does not issue extra orders.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-007-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No strategy backtest, new broker integration, or trading cadence reduction that sacrifices protections.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
