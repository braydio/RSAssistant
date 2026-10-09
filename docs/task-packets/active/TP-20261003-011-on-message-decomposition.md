# TP-20261003-011: Decompose on_message.py into Services

**Packet ID:** TP-20261003-011  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-08  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-011-on-message-decomposition.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-010  
**Priority:** Normal  
**Controller:** TP-20261003-001  
**Authoring chat:** https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e  
**Refresh planning chat:** https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e  

## Refresh status

This packet has been **structure-refreshed on 2026-10-08** against the current remotely visible `origin/main` handler surface.

Important dependency discrepancy:

- the user reports TP-20261003-010 has landed;
- the remotely visible GitHub `main` available during this refresh still points to `6c4a1da36405a7816d060d7c2bdc4b784f3f311c`;
- that remote tree still contains a large `utils/sql_utils.py` and does not expose the expected post-TP-010 `rsassistant/persistence/` domain decomposition.

Therefore this packet now contains a concrete, low-discovery service extraction plan, but **must not be changed to Ready until the TP-010 implementation is visible in the execution checkout/current main and its persistence import seams are reconciled**.

At execution time, first verify:

```bash
git rev-parse HEAD
git log -1 --oneline
find rsassistant/persistence -maxdepth 2 -type f -print
rg -n "utils\.sql_utils|rsassistant\.persistence" rsassistant utils
```

If TP-010 is present locally/current-main but differs from this packet's assumptions, refresh only the persistence import references; do not rediscover the entire handler architecture.

If TP-010 is not visible, stop with:

```text
PLANNING REFRESH REQUIRED
Packet: TP-20261003-011
Reason: TP-010 is reported landed but its implementation is not visible in the execution checkout/current main.
Authoring chat: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e
Next action: expose/sync the landed TP-010 implementation, then refresh persistence seams only.
```

## Objective

Reduce `rsassistant/bot/handlers/on_message.py` from a ~49 KB mixed orchestration module into explicit application services while preserving Discord behavior, packeted persistence boundaries, and all existing command/message contracts.

This is a **behavior-preserving decomposition**. It is not a product redesign.

## Do not rediscover

The current handler surface has already been traced.

Current `rsassistant/bot/handlers/on_message.py` contains these concrete clusters:

### Reverse-split / round-up policy cluster

Symbols:

- `_resolve_round_up_snippet()`
- `_format_watch_date()`
- `_resolve_round_up_confirmation()`
- `_resolve_fractional_handling_text()`
- `_process_round_up_flow()`
- `build_policy_summary()`
- `OnMessagePolicyResolver.full_analysis()`

### Holdings refresh coordination cluster

Symbols/state:

- `_configured_brokers`
- `_configured_brokers_source`
- `_refresh_seen_brokers`
- `_refresh_discovered_brokers`
- `_refresh_completion_event`
- `_refresh_discovery_task`
- `_refresh_active`
- `_pending_alerts_by_broker`
- `_pending_sell_commands`
- `_pending_reverse_split_round_ups`
- `_refresh_summary_task`
- `_refresh_channel`
- `_normalize_broker_name()`
- `_load_configured_brokers_from_mappings()`
- `_ensure_configured_brokers_loaded()`
- `_set_configured_brokers_from_discovery()`
- `_reset_refresh_state()`
- `_reset_completion_state()`
- `_finalize_discovered_brokers_after_idle()`
- `_reset_discovery_timer()`
- `start_holdings_completion_tracking()`
- `reset_holdings_completion_tracking()`
- `wait_for_holdings_completion()`
- `finalize_holdings_refresh_if_complete()`
- `record_holdings_brokers()`
- `_await_refresh_window()`
- `start_refresh_window()`

### Watchlist audit / autobuy cluster

Symbols/state:

- `_audit_active`
- `_missing_summary`
- `enable_audit()`
- `disable_audit()`
- `get_audit_summary()`
- `compute_account_missing_tickers()`
- `_extract_order_queue_pairs()`
- `queue_missing_watchlist_autobuys()`
- `_audit_holdings()`
- `attempt_autobuy()`

### Holdings alert decision/cache cluster

Symbols/state:

- `_one_share_positions`
- `_one_share_updated`
- `is_broker_ignored()`
- `is_tracked_reverse_split()`
- `record_one_share_position()`
- `get_one_share_positions()`
- `one_share_cache_fresh()`
- `clear_one_share_position()`
- alert threshold / AREB / auto-sell decision logic currently embedded inside `handle_primary_channel()`

### Discord edge/routing that stays in bot layer

Keep in `rsassistant/bot/handlers/on_message.py` unless a tiny bot-layer helper is clearer:

- `set_channels()`
- `on_message_ready()`
- `on_message_refresh_status()`
- `on_message_set_channels()`
- `handle_on_message()`
- `handle_primary_channel()`
- `handle_secondary_channel()`
- actual `channel.send(...)`
- `resolve_message_destination()`, `resolve_reply_channel()`, `resolve_watchlist_channel()`
- trusted-bot update/revert routing
- Discord chunking/mention presentation

## Architecture boundary

Target:

```text
rsassistant/bot/
    handlers/on_message.py       Discord routing + I/O edge

rsassistant/services/
    holdings_refresh.py          refresh lifecycle/state
    watchlist_audit.py           missing-position/audit/autobuy decisions
    holdings_alerts.py           holdings alert/cache decisions
    reverse_split_policy.py      policy/round-up domain interpretation
```

Do not create all four modules merely to satisfy this list if a landed TP-010 or current tests prove two responsibilities belong together. Do not collapse unrelated responsibilities back into one giant `services/on_message.py`.

Persistence remains owned by the post-TP-010 `rsassistant/persistence/` modules. Service modules must not create a new DB abstraction and must not import `utils.sql_utils` if TP-010 has removed production dependence on it.

## 1. Extract holdings refresh coordination

File:

`rsassistant/services/holdings_refresh.py`

Replace the handler's loose refresh globals with one explicit coordinator/state object.

Recommended shape:

```python
@dataclass
class HoldingsRefreshState:
    active: bool = False
    configured_brokers: set[str] = field(default_factory=set)
    configured_brokers_source: str | None = None
    seen_brokers: set[str] = field(default_factory=set)
    discovered_brokers: set[str] = field(default_factory=set)
    pending_alerts_by_broker: dict[str, dict[str, float]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    pending_sell_commands: list[str] = field(default_factory=list)
    pending_reverse_split_round_ups: bool = False
    refresh_channel: object | None = None
```

The exact task/event objects may remain coordinator attributes but should not be serialized or persisted.

Recommended class API:

```python
class HoldingsRefreshCoordinator:
    def start_completion_tracking(...)
    def reset_completion_tracking(...)
    async def wait_for_completion(...)
    def record_brokers(...)
    def begin_summary_window(...)
    def buffer_alert(...)
    def buffer_sell_command(...)
    def mark_reverse_split_round_up(...)
    def snapshot_summary(...)
    def reset(...)
```

Keep actual Discord sends in the handler. The service should return summary data/actions rather than sending messages itself where practical.

Preserve calls into the landed holdings refresh persistence API:

- `begin_holdings_refresh`
- `finalize_holdings_refresh`
- `holdings_refresh_in_progress`

If TP-010 moved these functions, use the landed repository/service import path. Do not restore old compatibility imports merely to match this packet.

## 2. Extract watchlist audit decisions

File:

`rsassistant/services/watchlist_audit.py`

Move pure/domain logic:

- missing ticker computation;
- queued ticker/broker duplicate suppression;
- broker normalization used only by audit;
- autobuy intent construction.

Recommended data contract:

```python
@dataclass(frozen=True)
class AutobuyIntent:
    ticker: str
    broker: str
    quantity: float
```

Recommended pure function:

```python
def build_missing_autobuy_intents(
    missing_by_account,
    queued_pairs,
    ignored_brokers,
) -> list[AutobuyIntent]:
    ...
```

The handler remains responsible for converting intents into Discord/order execution calls.

Do not pass a Discord `Bot`, `Message`, `Context`, or channel into the pure service.

Audit state may use a small `WatchlistAuditState` object instead of module globals.

Preserve visible behavior of:

- `enable_audit()`
- `disable_audit()`
- `get_audit_summary()`

Compatibility wrappers may remain in `on_message.py` temporarily if tests/importers depend on them.

## 3. Extract holdings alert decisions

File:

`rsassistant/services/holdings_alerts.py`

Move:

- ignored broker/ticker decisions;
- tracked reverse-split check adapter;
- one-share cache;
- AREB threshold decision;
- generic holdings threshold decision;
- optional auto-sell intent generation.

Recommended result contract:

```python
@dataclass(frozen=True)
class HoldingAlertDecision:
    broker: str
    account_name: str
    ticker: str
    price: float
    quantity: float
    areb_threshold_hit: bool
    generic_alert: bool
    reverse_split_one_share: bool
    sell_command: str | None
```

Keep Discord string rendering/mentions/chunking at the handler edge.

Do not change the meaning of:

- `AUTO_SELL_LIVE`
- `HOLDING_ALERT_MIN_PRICE`
- `IGNORE_TICKERS`
- `IGNORE_BROKERS`
- `try_record_action_today()`

## 4. Extract reverse-split policy interpretation

File:

`rsassistant/services/reverse_split_policy.py`

Move pure policy interpretation/render data:

- round-up snippet resolution;
- confirmation resolution;
- fractional handling text;
- watch-date normalization;
- policy summary data assembly.

Keep channel fallback and `send()` in the handler.

The current synchronous:

```python
OnMessagePolicyResolver.full_analysis(...)
```

may perform network/LLM work. In `handle_secondary_channel()`, execute it off the Discord event loop:

```python
policy_info = await asyncio.to_thread(
    OnMessagePolicyResolver.full_analysis,
    url,
    ticker_hint=ticker,
    fallback_text=message.content,
)
```

If the landed resolver API differs, use its real signature.

Do not rewrite the policy resolver's networking stack in this packet.

## 5. Keep autobuy scheduling at a clean boundary

`attempt_autobuy()` currently mixes:

- market calendar decision;
- config lookup;
- order intent creation;
- UUID creation;
- `bot.loop.create_task(schedule_and_execute(...))`;
- Discord confirmation messages.

Extract planning into a service function that returns scheduled order intents.

Recommended contract:

```python
@dataclass(frozen=True)
class ScheduledBuyIntent:
    order_id: str
    ticker: str
    quantity: float
    broker: str
    execution_time: datetime
    excluded_brokers: tuple[str, ...] = ()
```

The handler then:

1. asks service for intents;
2. schedules `schedule_and_execute(...)`;
3. sends confirmations.

Do not change market-open/next-open semantics.

## 6. Handler reduction target

The goal is not an arbitrary line-count contest, but the current ~49 KB handler should become primarily routing/presentation code.

Target outcome:

- `handle_primary_channel()` orchestrates parse → service decision → Discord response;
- `handle_secondary_channel()` orchestrates alert parse → threaded policy analysis → service interpretation → Discord response;
- global mutable business state is materially reduced;
- no service requires Discord Context/Message.

Do not move formatting helpers that are purely Discord presentation just to reduce line count.

## Compatibility

Before moving any public helper, search exact imports:

```bash
rg -n "from rsassistant\.bot\.handlers\.on_message import|on_message\." unittests rsassistant utils plugins
```

Where tests or production modules import helpers directly, either:

- update them to the new service module; or
- leave a small compatibility re-export/wrapper in `on_message.py`.

Do not preserve compatibility via duplicated implementations.

## Tests

Preserve and run at minimum:

- `unittests/on_message_utils_test.py`
- `unittests/on_message_roundup_flow_test.py`
- `unittests/watchlist_autobuy_audit_test.py`
- `unittests/tagged_alerts_test.py`
- policy resolver tests
- order scheduling tests touched by autobuy extraction

Add focused service tests:

- `unittests/holdings_refresh_service_test.py`
- `unittests/watchlist_audit_service_test.py`
- `unittests/holdings_alerts_service_test.py`
- `unittests/reverse_split_policy_service_test.py`

Tests should use plain values/fakes. Service tests must not require a live Discord client, network, broker, or LLM.

Required async regression:

- prove policy `full_analysis` is invoked through `asyncio.to_thread` or equivalent non-blocking boundary.

## Non-goals

- no persistence schema changes;
- no parser decomposition;
- no policy-rule redesign;
- no trading strategy changes;
- no Discord command renaming;
- no user-visible copy rewrite except trivial movement required to preserve exact current output;
- no aiohttp/network-client rewrite;
- no broad cleanup of unrelated utility modules.

## Implementation order

1. verify TP-010 is actually present in the execution checkout and reconcile persistence imports;
2. inventory external imports of `on_message.py` helpers;
3. add `rsassistant/services/` package if absent;
4. extract refresh coordinator + tests;
5. extract watchlist audit/autobuy decisions + tests;
6. extract holdings alert decisions/cache + tests;
7. extract reverse-split policy interpretation + threaded analysis boundary + tests;
8. reduce handler to routing/presentation and add compatibility wrappers only where required;
9. focused tests;
10. full validation;
11. write `docs/task-packets/summaries/TP-20261003-011-SUMMARY.md`.

## Acceptance criteria

- [ ] execution checkout visibly contains TP-010 before implementation begins.
- [ ] `on_message.py` is materially smaller and primarily Discord-edge code.
- [ ] service modules contain no Discord `Message`/`Context` dependency.
- [ ] persistence imports use the landed TP-010 domain modules, not a re-expanded `utils.sql_utils`.
- [ ] refresh lifecycle state is owned by an explicit service/coordinator rather than a large family of handler globals.
- [ ] watchlist audit/autobuy decisions are testable without Discord.
- [ ] holdings alert decisions/cache are testable without Discord.
- [ ] policy interpretation is separated from channel posting.
- [ ] synchronous policy analysis no longer directly blocks the Discord event loop.
- [ ] existing user-visible behavior remains stable.
- [ ] compatibility wrappers, if any, contain no duplicated business implementation.
- [ ] focused and full test suites pass or unrelated baseline failures are documented precisely.
- [ ] durable packet summary exists and includes the exact Authoring chat URL.

## Validation

Focused:

```bash
python -m pytest -q \
  unittests/on_message_utils_test.py \
  unittests/on_message_roundup_flow_test.py \
  unittests/watchlist_autobuy_audit_test.py \
  unittests/tagged_alerts_test.py \
  unittests/holdings_refresh_service_test.py \
  unittests/watchlist_audit_service_test.py \
  unittests/holdings_alerts_service_test.py \
  unittests/reverse_split_policy_service_test.py
```

Then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

## Completion summary / response contract

Write:

`docs/task-packets/summaries/TP-20261003-011-SUMMARY.md`

It must include:

```text
Authoring chat: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e
```

and the `Process Feedback` + `Next Handoff` structure required by `AGENTS.md`.

Expected next packet:

- TP-20261003-012
- state: refresh-required until TP-011 implementation is reviewed
- ChatGPT/user planning refresh required: yes
- Authoring chat: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Final user-facing response must include the same exact Authoring chat URL.
