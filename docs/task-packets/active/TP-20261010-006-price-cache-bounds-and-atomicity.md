# TP-20261010-006: Bound Market Price Cache and Minimize Disk Writes

**Packet ID:** TP-20261010-006  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-006-price-cache-bounds-and-atomicity.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** Normal  
**Authoring chat:** not-recorded  

## Objective

Reduce bound market price cache and minimize disk writes overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `utils/price_fetcher.py`
- `utils/config_utils.py`
- `config/.env.example`
- `unittests/price_fetcher_test.py`
- `docs/architecture.md`

## Confirmed current behavior

`_CACHE` and `_FAILED_ATTEMPTS` in `utils/price_fetcher.py` grow without a bound; `_save_cache_to_file()` rewrites the entire `yfinance_price_cache.json` on successful refresh. TTL and backoff are 600s; batches are 50; failures currently return any prior cached value.

## Required changes and implementation order

1. Add a bounded/pruned cache default max 1,000 tickers and an explicit stale-retention ceiling appropriate to normal watchlists; evict oldest timestamps using deterministic order. Clear old `_FAILED_ATTEMPTS` after backoff. Keep existing 10-minute fresh TTL and API contracts.
2. Persist only on successful cache change; write compact JSON to a sibling temp file, flush and `os.replace()` atomically so interruption cannot truncate live cache. Do not recreate directory on every successful call.
3. Guard file cache against malformed/untrusted data and unreasonable item count; normalize cached symbols and reject invalid price/ts values. Avoid re-downloading duplicate tickers already handled by `dict.fromkeys`.
4. Limit simultaneous thread-worker fetches of the same symbol/batch with a small single-flight mechanism, without holding a global lock during network I/O. Avoid introducing event-loop locks into sync API.
5. Explicitly preserve legacy stale-return behavior for API callers in this packet and document age limits; pricing used for order decisions must never silently become more stale than before. If a stricter trading quote policy is required, stop for separate review rather than changing trading semantics silently.

## Focused tests and validation

Test >1,000 symbols eviction, retry expiration, bad cache JSON, atomic replace failure, concurrent duplicate fetch coalescing, 50-symbol batching, prior-value fallback. `python -m pytest -q unittests/price_fetcher_test.py unittests/parsing_utils_test.py`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] Cache size bounded on disk and memory; at most one successful rewrite per updated fetch; no partial JSON on interruption; current price caller behavior preserved.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-006-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No switch to premium data, no artificial slower refresh for trading prices.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
