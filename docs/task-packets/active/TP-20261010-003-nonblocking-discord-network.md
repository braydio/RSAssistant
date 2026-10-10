# TP-20261010-003: Keep Network and Disk Operations off Discord Event Loop

**Packet ID:** TP-20261010-003  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-003-nonblocking-discord-network.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** High  
**Authoring chat:** not-recorded  

## Objective

Reduce keep network and disk operations off discord event loop overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `rsassistant/bot/handlers/on_message.py`
- `rsassistant/bot/cogs/holdings.py`
- `utils/watch_utils.py`
- `utils/policy_resolver.py`
- `utils/parsing_utils.py`
- `utils/price_fetcher.py`
- `unittests/on_message_roundup_flow_test.py`
- `unittests/price_fetcher_test.py`
- `unittests/nonblocking_runtime_test.py (new)`

## Confirmed current behavior

`handle_secondary_channel()` calls sync `alert_channel_message()` and `OnMessagePolicyResolver.full_analysis()`; the resolver and SEC helpers use `requests.get()`, and `utils/openai_utils.extract_reverse_split_details()` uses `requests.post()`. `WatchListManager.list_watched_tickers(include_prices=True)` and `send_watchlist_prices()` invoke sync `get_last_prices()` from async commands. `HoldingsCog.holdings_snapshot()` calls sync importer directly. In contrast, primary-channel order parsing already uses `asyncio.to_thread(parse_order_message,...)`; preserve that existing protection.

## Required changes and implementation order

1. Wrap the full secondary alert parse/policy-resolution chain in a single bounded `asyncio.to_thread` worker function, returning plain data; all Discord `send` operations stay on the event loop. Use an `asyncio.Semaphore(2)` for expensive policy network calls, and timeouts in existing sync HTTP helpers. Do not wait with a blocking lock on the event loop.
2. For watchlist pricing, await `asyncio.to_thread(get_last_prices, tuple(watch_list))` once per command, then build embeds in the event loop. Do not individually fetch per ticker.
3. For `HoldingsCog.holdings_snapshot()`, move `import_holdings_if_updated` and `build_holdings_snapshot_embeds` disk-heavy preparation into a worker only when no Discord object is mutated off-thread; if embedding in worker is unsafe, return plain rows then construct embeds on-loop.
4. Preserve error policy: network failure must produce a bounded failure response, never queue a buy/sell or silently affirm a round-up. Keep SEC/NASDAQ result precedence and dedupe behavior unchanged.
5. Do not move primary holdings persistence in this packet; that intersects the existing TP-20261003-006/007 and TP-20261003-011 migration train.

## Focused tests and validation

Patch slow sync callables with thread Events to prove `asyncio.sleep(0)`/a heartbeat probe proceeds while the operation runs; verify maximum concurrent policy analyses, returned policy equality, error handling, and no extra orders. `python -m pytest -q unittests/nonblocking_runtime_test.py unittests/on_message_roundup_flow_test.py unittests/price_fetcher_test.py`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] The named async boundaries never directly execute sync network fetches and remain responsive during induced 2-second mock stalls.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-003-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No wholesale conversion from requests to aiohttp; no change to LLM provider, trading decisions, or TP-011 service decomposition.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
