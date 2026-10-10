# TP-20261010-010: Replace Per-Ticker Holdings CSV Scans with One SQL Read

**Packet ID:** TP-20261010-010  
**Status:** Draft  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-010-holdings-summary-single-pass.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** TP-20261003-007 and TP-20261003-011 (dependency refresh required)  
**Priority:** High  
**Authoring chat:** not-recorded  

## Objective

Reduce replace per-ticker holdings csv scans with one sql read overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `rsassistant/bot/cogs/holdings.py`
- `utils/utility_utils.py`
- `utils/sql_utils.py (current baseline only)`
- `rsassistant/persistence/holdings.py (expected after TP-010 migration)`
- `unittests/utility_utils_test.py`
- `unittests/holdings_cog_test.py`

## Confirmed current behavior

`HoldingsCog.show_reminder()` loops `for ticker in watch_list.keys(): await track_ticker_summary(...,collect=True)`. `track_ticker_summary()` loads account mappings and scans `HOLDINGS_LOG_CSV` for each ticker, producing O(number_of_tickers × CSV_rows) reads plus repeated mapping loads. Existing TP-20261003-006/007 will change holdings authority and TP-20261003-011 will extract handler/services; do not optimize the obsolete CSV path as a new authority.

## Required changes and implementation order

1. After TP-007 and TP-011 merge, inspect only the landed holdings repository read API and the preserved `track_ticker_summary` contract. Resolve current symbol names during dependency refresh; **do not guess future SQLite table names as implemented facts**.
2. Add a repository query that loads the latest committed holdings snapshot and mapped configured accounts once. Compute a per-ticker/per-broker status index in one Python pass; preserve quantity > 0 semantics, account aliases, timestamp footer, and configured-but-missing account denominators.
3. Update `HoldingsCog.show_reminder()` to request all watchlist summaries in one operation and render without per-ticker SQL/CSV calls. Preserve the single-ticker public `track_ticker_summary` behavior via an adapter that can delegate to the shared batch helper.
4. Add query-count assertion using mocked repository and performance test for 10 and 100 tickers. Never build a cache that presents incomplete refresh as committed holdings.
5. **Refresh gate**: compare new persistence and TP-011 service boundaries before changing status to Ready; if incompatible, update packet and tracker and stop.

## Focused tests and validation

Focused holdings reporting tests for 0, 1, 100 tickers, missing brokers, remapped accounts, duplicate ticker rows, failed/incomplete refresh, and one query per snapshot. Run `python -m pytest -q unittests/utility_utils_test.py unittests/holdings_cog_test.py` and new batch tests.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] One committed snapshot fetch per report rather than one full CSV scan per ticker, with byte-identical status semantics for fixtures.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-010-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No new performance-history schema, no trading changes, no reverting TP-007 SQL authority.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
