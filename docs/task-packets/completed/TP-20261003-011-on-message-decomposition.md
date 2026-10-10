# TP-20261003-011: Decompose on_message.py into Services

**Packet ID:** TP-20261003-011
**Status:** Complete
**Created:** 2026-10-03
**Last updated:** 2026-10-08
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/completed/TP-20261003-011-on-message-decomposition.md`
**Workstream size:** One implementation packet
**Depends on:** TP-20261003-010
**Priority:** Normal
**Controller:** TP-20261003-001

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-010 landed**. Dependency refresh completed on 2026-10-08 before implementation.

Before coding:

1. re-open current `main` and preserve the existing local worktree;
2. read TP-20261003-010's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, stop before implementation and update this packet or report the exact blocker;
5. record the review link for traceability:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Historical suggested handoff wording:

> TP-20261003-010 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

### Refresh findings

- TP-010 is complete locally and its new `accounts.py`, `watchlists.py`, `reverse_splits.py`, `admin.py`, and `runtime.py` modules do not change message-handler behavior or introduce a persistence dependency for the services proposed here.
- `utils/sql_utils.py` is now compatibility-only and production Python imports of it are zero. The handler still reaches established utility facades for parsing, holdings refresh, watchlists, orders, policy, and split-watch operations; this packet does not need to migrate persistence.
- `rsassistant/bot/handlers/on_message.py` exists at the named path and is 1,370 lines. Its current cohesive clusters include pure alert/mention/policy formatting, holdings refresh aggregation and broker completion tracking, one-share position/audit state, watchlist autobuy orchestration, and round-up flow.
- `rsassistant/services/` does not yet exist. Create it only for extracted non-Discord orchestration; keep Discord channel resolution and sends in the handler.
- No schema or public persistence API assumptions in this packet conflict with TP-010. Proceed with implementation, extracting only seams verified against the current symbols.


## Objective

Reduce `rsassistant/bot/handlers/on_message.py` from a large mixed orchestration module by extracting application services while keeping Discord-specific I/O in the bot layer.

## Architecture boundary

`rsassistant/bot/` owns:

- Discord Message/Context objects;
- channel resolution;
- reactions;
- sends/replies;
- command routing.

`rsassistant/services/` owns:

- domain orchestration using plain values/data structures;
- policy pipeline coordination;
- holdings refresh orchestration;
- order orchestration;
- alert processing.

Persistence stays in `rsassistant/persistence/`.

## Target service candidates

Create only services justified by current symbols after dependency refresh. Likely:

```text
rsassistant/services/alert_processing.py
rsassistant/services/order_orchestration.py
rsassistant/services/holdings_refresh.py
rsassistant/services/policy_orchestration.py
```

Do not create empty architecture folders/classes for aesthetics.

## Extraction method

Use behavior-preserving extraction:

1. identify cohesive private/helper clusters in `on_message.py`;
2. move pure/domain orchestration first;
3. pass primitive values/dataclasses into services;
4. return result objects/actions;
5. keep actual Discord sends/reactions at handler edge.

Example result contract:

```python
@dataclass
class AlertDecision:
    ticker: str
    action: str | None
    reason: str
    messages: list[str]
```

Do not force this exact dataclass if current code has a better established result shape.

## Blocking work

During extraction, identify synchronous network/LLM/policy calls directly invoked on the Discord event loop.

Where a service remains synchronous and blocking, wrap at the async boundary:

```python
result = await asyncio.to_thread(service_fn, ...)
```

Do not rewrite whole clients to aiohttp in this packet.

## Tests

Preserve existing:

- `unittests/on_message_utils_test.py`;
- `unittests/on_message_roundup_flow_test.py`;
- tagged alerts;
- policy resolver;
- command/cog behavior.

Add service-level tests with plain values and mocked persistence/network boundaries.

## Non-goals

- no policy rule redesign;
- no persistence changes;
- no parser decomposition;
- no Discord command renaming;
- no user-visible wording rewrite unless required by extraction tests.

## Acceptance criteria

- [x] `on_message.py` is materially smaller.
- [x] domain services do not require Discord Message/Context.
- [x] Discord I/O stays at handler edge.
- [x] blocking service calls do not directly block event loop.
- [x] packet behavior tests pass.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

- `rsassistant/bot/handlers/on_message.py` decreased from 1,370 to 1,175 lines (195 net lines removed).
- Added `rsassistant/services/alert_processing.py` for alert tagging and formatting, round-up policy interpretation, account holdings gaps, and plain-value holdings alert classification with injected policy/persistence callbacks.
- Added `rsassistant/services/order_orchestration.py` for duplicate/ignored broker filtering and standard/override autobuy order planning. The handler retains channel resolution, scheduling, and Discord sends.
- Added `rsassistant/services/policy_orchestration.py` around the existing policy resolver. The secondary-channel handler now runs its synchronous network/model `full_analysis` call through `asyncio.to_thread`; order parsing already used a worker thread.
- Discord channel selection, replies/sends, refresh timer tasks, refresh/audit lifecycle state, and round-up watchlist updates remain in the bot handler because they directly coordinate Discord and event-loop state.
- Compatibility helper names remain in `on_message.py` and delegate to service functions so existing imports and tests continue to work.
- Tightened body-derived round-up snippet trimming to begin at the fractional-share clause and end at a whole word when length-limited; the existing `on_message_utils_test.py` expectation now passes.
- Added plain-value service tests in `unittests/services/` for alert classification, missing tickers, tagged-alert rules, autobuy planning, and duplicate filtering.
- Focused tests including `unittests/policy_resolver_test.py`, `unittests/on_message_utils_test.py`, `unittests/on_message_roundup_flow_test.py`, `unittests/tagged_alerts_test.py`, `unittests/watchlist_autobuy_audit_test.py`, and service tests: 27 passed.
- `python -m unittest discover -s unittests -p '*_test.py'`: 89 tests passed.
- `python -m compileall -q rsassistant utils plugins unittests`: passed.
- `python -m pytest -q`: 159 passed, 6 failed. The failures are outside this handler work: `all_command_test.py` and `brokerwith_command_test.py` expect `RSAssistant` module exports that are absent; two `order_remove_command_test.py` cases call decorated commands with a missing context; and two `sell_queue_command_test.py` cases expect the same absent top-level module exports. These were not changed.
