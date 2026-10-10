# TP-20261010-002: Replace Threaded Scheduler with Asyncio-Native Jobs

**Packet ID:** TP-20261010-002  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-002-asyncio-native-scheduler.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** High  
**Authoring chat:** not-recorded  

## Objective

Reduce replace threaded scheduler with asyncio-native jobs overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `rsassistant/bot/tasks.py`
- `utils/refresh_scheduler.py`
- `utils/market_calendar.py`
- `unittests/refresh_scheduler_test.py`
- `unittests/order_queue_tasks_test.py`
- `unittests/scheduler_lifecycle_test.py (new)`

## Confirmed current behavior

`_start_reminder_scheduler()` starts `BackgroundScheduler` with thread-to-`bot.loop.create_task` lambdas, at 08:45/15:30 reminders and 07:00 past-due reconciliation; it also polls holdings every five minutes. `run_total_refresh_scheduler()` is already an independent async loop and only starts when `ENABLE_MARKET_REFRESH` is true.

## Required changes and implementation order

1. Use APScheduler 3.11 `AsyncIOScheduler(event_loop=asyncio.get_running_loop(), timezone=MARKET_TZ)`, `CronTrigger(..., timezone=MARKET_TZ)`, and explicit `id`, `replace_existing=True`, `max_instances=1`, `coalesce=True`. Register coroutine functions directly, not lambdas calling `loop.create_task`.
2. Keep exact 08:45, 15:30, and 07:00 America/New_York times and DST behavior. Keep `run_total_refresh_scheduler` separate in this packet, with existing opt-in cadence.
3. Register holdings import interval only if `AUTO_RSA_HOLDINGS_ENABLED` is true. Because import is synchronous disk/SQLite work, wrap it in an async callable that awaits `asyncio.to_thread(import_holdings_if_updated)`; do not run it in the event loop.
4. Preserve `BackgroundTasks` shutdown handle but change its scheduler type; initialize scheduler once in `setup_hook`, guard duplicate starts, and stop cleanly even if job cancellation occurs.
5. Include a job-error listener or exception wrapper with redacted metadata and ensure a failing job cannot terminate scheduler.

## Focused tests and validation

Use fake clock/scheduler and mocks to verify 3 cron times, enabled/disabled polling, one instance during restart/reconnect, no threaded scheduler, no simultaneous same job, graceful shutdown, and deterministic DST transitions. `python -m pytest -q unittests/refresh_scheduler_test.py unittests/order_queue_tasks_test.py unittests/scheduler_lifecycle_test.py`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] No `BackgroundScheduler` or thread bridge remains in bot scheduling. Existing job behavior and order timing preserved with nonoverlapping execution.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-002-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No change to trade execution cadence or default ENABLE_MARKET_REFRESH setting; no holdings schema changes.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
