# TP-20261003-011: Decompose on_message.py into Services

**Packet ID:** TP-20261003-011
**Status:** Draft
**Created:** 2026-10-03
**Last updated:** 2026-10-03
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/active/TP-20261003-011-on-message-decomposition.md`
**Workstream size:** One implementation packet
**Depends on:** TP-20261003-010
**Priority:** Normal
**Controller:** TP-20261003-001

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-010 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-010's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-010 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


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

- [ ] `on_message.py` is materially smaller.
- [ ] domain services do not require Discord Message/Context.
- [ ] Discord I/O stays at handler edge.
- [ ] blocking service calls do not directly block event loop.
- [ ] behavior tests remain green.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report lines/major clusters removed from `on_message.py`, service modules created, any remaining mixed-responsibility blocks, async boundaries, and tests.
