# TP-20261010-001: Runtime Resource Baseline and Regression Instrumentation

**Packet ID:** TP-20261010-001  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-001-runtime-resource-baseline.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** High  
**Authoring chat:** not-recorded  

## Objective

Reduce runtime resource baseline and regression instrumentation overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `rsassistant/bot/core.py`
- `rsassistant/bot/tasks.py`
- `utils/logging_setup.py`
- `utils/performance_metrics.py (new)`
- `config/.env.example`
- `unittests/performance_metrics_test.py (new)`
- `docs/resource-performance-baseline.md (new)`

## Confirmed current behavior

The bot starts background work in `RSAssistantBot.setup_hook()` and uses `utils/logging_setup.start_heartbeat_writer()`. There is no reproducible CPU/RSS/event-loop lag or outbound-call baseline in the repository. Do not claim measured savings until a baseline exists.

## Required changes and implementation order

1. Add opt-in `RESOURCE_METRICS_ENABLED=false` and `RESOURCE_METRICS_INTERVAL_SECONDS=300`, parsed in `utils/config_utils.py`. Default must avoid a new always-on task.
2. In `utils/performance_metrics.py`, implement a narrow metrics snapshot with `time.process_time()`, `time.monotonic()`, event-loop drift using `loop.time()` and `asyncio.sleep()`, `len(asyncio.all_tasks())`, and RSS from `/proc/self/status` when present (fallback unavailable, not zero). Sample at most once per configured interval; log one structured summary only, without ticker, account, or message text.
3. Wire a cancellable metrics task from `start_background_tasks()` into `BackgroundTasks` and `stop_background_tasks()`; do not create one per reconnection.
4. Instrument existing outbound paths by monotonic duration/counters only where easy, starting with holdings-import attempts, policy-resolution call duration, and yfinance batch requests. Avoid global monkeypatches and metric labels with unbounded ticker/URL cardinality.
5. Document reproducible baseline runs in `docs/resource-performance-baseline.md`: idle for 30 minutes, market refresh simulation with mocked network, 10/100 ticker workloads, startup, shutdown, and 24-hour retained logs. Record p50/p95 event-loop drift, process CPU time, RSS, request counts, files written, and disk bytes before/after. Leave numeric observations blank until actually measured.

## Focused tests and validation

`unittests/performance_metrics_test.py`: disabled by default; sample formatting, unavailable RSS, bounded labels, cancellation, duplicate scheduler startup. Run `python -m pytest -q unittests/performance_metrics_test.py unittests/refresh_scheduler_test.py` and `python -m compileall -q rsassistant utils`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] A disabled-by-default telemetry path with deterministic tests and a documented repeatable baseline. No sample can trigger an order, external request, or sensitive payload logging.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-001-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No speculative performance percentage; no Prometheus stack, new database, or production profiling without operator opt-in.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
