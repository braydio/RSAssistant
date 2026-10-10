# TP-20261004-002: Performance Visibility and Growth History

**Packet ID:** TP-20261004-002  
**Status:** Ready  
**Created:** 2026-10-04  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261004-002-performance-visibility.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-007, TP-20261004-001  
**Priority:** High  
**Controller:** TP-20261003-001  
**Authoring chat:** https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e  
**Refresh planning chat:** https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e  
**Refreshed against main:** `6daebbabb135f2d346057d94343b158481633a79`  

## Dependency-refresh checkpoint — resolved

This packet has been refreshed against the actual landed holdings-authority and performance-history implementations.

Confirmed landed seams:

### Performance repository

File:

`rsassistant/persistence/performance.py`

Available APIs:

```python
list_account_value_snapshots(
    account_ids=None,
    start_at=None,
    end_at=None,
    *,
    database=None,
) -> list[dict]

latest_account_values(
    account_ids=None,
    *,
    database=None,
) -> list[dict]

account_value_series(
    account_id,
    start_at=None,
    end_at=None,
    *,
    database=None,
) -> list[dict]

portfolio_value_series(
    start_at=None,
    end_at=None,
    *,
    database=None,
) -> list[dict]

backfill_historical_account_values(
    *,
    database=None,
) -> int
```

Snapshot rows expose:

```text
snapshot_id
refresh_id
account_id
observed_at
positions_value
reported_account_total
effective_value
valuation_basis
source
```

Valuation basis values currently emitted:

```text
reported_total
positions_sum
historical_positions_sum
```

### Holdings semantics

TP-20261003-006/007 landed a full-replace holdings lifecycle.

Each live holdings refresh now records account-value snapshots in the same transaction that commits `holdings_current`.

Historical backfill:

- reads `HistoricalHoldings`;
- groups by `(account_id, date)`;
- writes one row per account/date;
- uses deterministic IDs:
  `historical:<date>:<account_id>`;
- uses `valuation_basis="historical_positions_sum"`;
- is idempotently gated through `legacy_imports`.

### Important historical-series caveat

Do **not** use the landed `portfolio_value_series()` directly as the sole source for historical charts.

Live snapshots share one refresh ID across accounts, but the historical backfill deliberately uses one refresh ID **per account/day**.

Therefore:

```text
GROUP BY refresh_id
```

is valid for live refreshes but does not produce one historical whole-portfolio point per date.

TP-002 must build a normalized observation series from
`list_account_value_snapshots()` so historical rows can be combined by date while live rows remain grouped by refresh.

Do not change the TP-001 storage schema merely to work around this presentation concern.

### Current historical coverage

The production backfill function exists but TP-001 did **not** run it against the production database.

History starts accumulating from live holdings refreshes automatically.

This packet must wire the one-time idempotent historical backfill into the performance feature so the operator receives historical visibility without a separate shell operation.

## Objective

Give the operator immediate Discord visibility into:

- current portfolio/account value;
- recent value growth;
- historical value trajectory;
- account/broker contribution;
- data coverage;
- valuation basis.

This is a visibility layer over the landed account-value history. It must not invent cash-flow-adjusted investment returns.

## Metric semantics

Use:

```text
Current value
Value change
Value growth
Positions value
Reported account value
```

Do not call balance/value change:

```text
investment return
rate of return
portfolio return
performance return
```

RSAssistant does not currently model external deposits/withdrawals reliably.

Valid:

```text
30D value change: +$914.28 (+7.66%)
```

Not valid:

```text
30D investment return: +7.66%
```

## Architecture

Add:

```text
rsassistant/services/performance.py
rsassistant/bot/cogs/performance.py
unittests/performance_service_test.py
unittests/performance_cog_test.py
```

Update:

```text
rsassistant/persistence/accounts.py
rsassistant/bot/core.py
rsassistant/bot/cogs/holdings.py
README.md
```

Do not put performance comparison math in the Discord cog.

### Layer ownership

`rsassistant/persistence/performance.py`

- durable snapshot reads/backfill only.

`rsassistant/services/performance.py`

- window parsing;
- scope resolution;
- observation normalization;
- endpoint selection;
- common-account comparison;
- value delta/percentage math;
- coverage/basis metadata.

`rsassistant/bot/cogs/performance.py`

- Discord command parsing;
- embed/text formatting;
- chart rendering;
- file send;
- operator-facing errors/help.

## 1. Add reusable account identity query

File:

`rsassistant/persistence/accounts.py`

Current `fetch_account_labels()` returns only account ID + nickname, which is insufficient for broker filtering.

Add:

```python
def fetch_account_identities(*, database=None) -> list[dict]:
    ...
```

Recommended query:

```sql
SELECT
    account_id,
    broker,
    broker_number,
    account_number,
    account_nickname
FROM Accounts
ORDER BY broker, broker_number, account_number
```

Return:

```python
{
    "account_id": int,
    "broker": str,
    "broker_number": str,
    "account_number": str,
    "account_nickname": str | None,
}
```

Export it from the module.

Do not put broker filtering SQL in the Discord cog.

## 2. Implement performance service

File:

`rsassistant/services/performance.py`

Recommended dataclasses:

```python
@dataclass(frozen=True)
class ValueObservation:
    observed_at: datetime
    account_values: dict[int, float]
    account_positions_values: dict[int, float]
    account_bases: dict[int, str]
    source_key: str

@dataclass(frozen=True)
class PerformanceSummary:
    window: str
    scope_label: str
    current_total: float
    comparable_current_total: float | None
    comparison_total: float | None
    value_change: float | None
    value_change_pct: float | None
    current_observed_at: datetime
    comparison_observed_at: datetime | None
    current_account_ids: tuple[int, ...]
    comparison_account_ids: tuple[int, ...]
    common_account_ids: tuple[int, ...]
    mixed_basis: bool
    current_bases: tuple[str, ...]
    comparison_bases: tuple[str, ...]
```

Exact names may vary, but keep the service plain-Python and Discord-free.

### Scope resolution

Support:

- no scope → full portfolio;
- numeric account ID;
- exact case-insensitive account nickname;
- exact case-insensitive broker name.

Resolution order:

1. numeric ID / exact nickname;
2. broker name.

A broker scope returns all matching account IDs.

If no scope matches, return a typed service error/result that the cog can render clearly.

Do not fuzzy-match financial account identities.

### Observation normalization

Load raw history with:

```python
list_account_value_snapshots(account_ids=selected_ids or None)
```

Build normalized observations.

For live rows:

```text
group key = ("refresh", refresh_id)
```

For historical-backfill rows:

```text
source == "historical_holdings_backfill"
group key = ("historical", observed_at calendar date)
```

For each normalized observation:

- one value per account;
- `observed_at` = latest row timestamp in the group;
- retain each account's valuation basis;
- retain positions value separately.

This ensures one historical portfolio point per date even though historical refresh IDs are account-specific.

Do not mutate persisted history or rewrite refresh IDs.

## 3. Comparison rules

Supported windows:

```text
1d
7d
30d
90d
ytd
1y
all
```

Default:

`30d`

Use the newest normalized observation as the current endpoint.

### Fixed windows

For:

- 1d
- 7d
- 30d
- 90d
- 1y

compute the target timestamp from the latest observation, then select the newest observation at or before the target.

If no observation exists at/before the target, the comparison is unavailable.

Do not silently use a much newer partial period and label it 30D.

### YTD

Target:

January 1 of the current observation's year.

Select:

1. latest observation at or before Jan 1 when available;
2. otherwise earliest observation after Jan 1.

If rule 2 is used, expose the actual comparison date so the UI can say the available YTD coverage begins later than Jan 1.

### All

Use the earliest normalized observation.

## 4. Protect against changing account coverage

Do not calculate whole-portfolio percentage growth by comparing unequal account sets.

For the selected scope:

```python
common_ids = current_account_ids & comparison_account_ids
```

Always report:

`current_total`

using all current accounts in scope.

For change math, calculate:

```python
comparable_current_total = sum(current values for common_ids)
comparison_total = sum(comparison values for common_ids)
value_change = comparable_current_total - comparison_total
```

Percentage:

```python
value_change_pct = value_change / comparison_total * 100
```

If:

- no common accounts; or
- comparison total == 0;

return percentage as unavailable.

Expose:

```text
current account count
comparison account count
common account count
```

so newly added/removed accounts cannot masquerade as growth.

## 5. Basis disclosure

Comparison may cross:

```text
historical_positions_sum → reported_total
historical_positions_sum → positions_sum
positions_sum → reported_total
```

Set:

`mixed_basis=True`

when valuation bases differ across the common comparison set or between endpoints.

Do not suppress the dollar/percentage comparison solely because of mixed basis, but label it clearly as mixed-basis value change.

Suggested UI:

```text
Basis: mixed
Older history uses position value; newer observations may include reported account totals/cash.
```

For same-basis comparisons, show the basis tersely.

## 6. Wire production historical backfill

File:

`rsassistant/bot/cogs/performance.py`

On cog load, run the landed idempotent backfill off the Discord event loop:

```python
async def cog_load(self) -> None:
    try:
        inserted = await asyncio.to_thread(backfill_historical_account_values)
        logger.info("Performance history backfill inserted %d row(s).", inserted)
    except Exception:
        logger.exception("Performance history backfill failed; live performance remains available.")
```

Rationale:

- TP-001 intentionally made backfill explicit/callable but did not wire it;
- the function is transactionally idempotent through `legacy_imports`;
- this packet owns historical visibility;
- users should not need a separate shell operation.

A backfill failure must **not** prevent the cog/bot from loading.

Do not repeatedly recalculate historical data after the ledger records completion.

## 7. Add Discord performance cog

File:

`rsassistant/bot/cogs/performance.py`

Register it in:

`rsassistant/bot/core.py`

Add to `_CORE_COGS`, preferably immediately after holdings:

```python
"rsassistant.bot.cogs.holdings",
"rsassistant.bot.cogs.performance",
```

Command:

```text
..performance [window] [scope...]
```

Aliases:

```text
..perf
..growth
```

Examples:

```text
..performance
..performance 7d
..performance ytd
..performance 30d Fidelity
..performance all IRA
```

Scope should consume the remaining command text so nicknames with spaces can resolve.

Recommended command signature:

```python
async def performance(
    self,
    ctx,
    window: str = "30d",
    *,
    scope: str | None = None,
)
```

If the first token is not a valid window, treat the entire argument string as scope with the default 30D window only if this can be implemented unambiguously and tested. Otherwise require explicit window before scope and return concise usage help.

## 8. Summary output

Keep the response compact.

Example:

```text
Portfolio Value · 30D

Current value            $12,842.17
Comparable current       $12,400.17
30D value change            +$914.28
30D change                    +7.96%
7D value change              +$221.42

Coverage
Current: 11 accounts
Compared: 10 common accounts
Sep 10, 2026 → Oct 10, 2026

Basis
Mixed: historical position value → reported account totals
```

Do not show `Comparable current` when current/comparison account sets are identical.

Add a secondary 7D quick-growth line when:

- requested window is not 7D; and
- a valid 7D comparison exists.

Do not manufacture the line when coverage is insufficient.

## 9. Current contributors

For full portfolio/broker views, show up to three largest current account contributors.

Use:

- account nickname when available;
- otherwise broker + account number fallback.

Do not expose full sensitive account identifiers if existing UI conventions mask/abbreviate them. Follow current account-display behavior.

This is current-value composition, not contribution-to-return attribution.

Do not label it "performance contribution."

## 10. Historical chart

Use matplotlib.

Primary plotted series:

`effective_value`

represented through normalized observations.

Rules:

- currency y-axis;
- requested window;
- title contains scope + window;
- annotate first/latest value when readable;
- chart data must use the same scope/coverage rules as summary;
- for portfolio plots, use total value for the accounts present at each observation;
- surface coverage changes in the Discord caption;
- mark or mention the first mixed-basis transition rather than pretending the line is perfectly homogeneous.

For `all`:

downsample **for display only** when needed.

Recommended deterministic display policy:

```text
<= 120 observations: plot all
121-730: one latest observation per day
> 730: one latest observation per week
```

Do not delete or aggregate source history in SQLite.

Render to `io.BytesIO`; do not write persistent chart files.

## 11. Preserve existing quantity history

File:

`rsassistant/bot/cogs/holdings.py`

Current `..history` remains quantity history over `HistoricalHoldings`.

Change help text from:

```text
Show historical holdings from the SQL log.
```

to something explicit such as:

```text
Show historical held quantity by account/ticker. Use ..performance for value growth.
```

Do not change its underlying query or chart semantics in this packet.

## Tests

### `unittests/performance_service_test.py`

Cover:

- raw live rows grouped by refresh ID;
- historical rows grouped by date across multiple accounts;
- 1d/7d/30d/90d/1y boundary selection;
- YTD prior-Jan-1 selection;
- YTD earliest-after-Jan-1 fallback;
- all-time earliest;
- positive/negative dollar change;
- percentage math;
- zero baseline;
- no comparison available;
- common-account-only delta;
- newly added account does not inflate growth;
- removed account handling;
- mixed valuation basis;
- account ID scope;
- nickname scope;
- broker scope;
- invalid scope.

### `unittests/performance_cog_test.py`

Cover:

- default 30D command;
- aliases registered;
- scope with spaces;
- insufficient-history response;
- chart attachment;
- backfill called through `asyncio.to_thread`;
- backfill failure does not prevent command availability;
- summary hides comparable-current line when account sets match;
- mixed-basis disclosure;
- no use of the phrase "investment return" in normal output.

Update:

`unittests/holdings_cog_test.py`

for clarified `..history` help only if help metadata is asserted.

## Non-goals

- no time-weighted return;
- no money-weighted/XIRR return;
- no deposits/withdrawals inference;
- no tax-lot P&L;
- no realized/unrealized gain engine;
- no benchmark comparison;
- no S&P 500 comparison;
- no web dashboard;
- no persistence schema changes unless an implementation-blocking defect is discovered;
- no rewrite of existing quantity-history behavior.

## Implementation order

1. verify `main` still contains migration 9 and the TP-001 APIs above;
2. add `fetch_account_identities()`;
3. implement normalized performance observation/service layer;
4. implement coverage-safe comparison math;
5. add service tests;
6. add PerformanceCog;
7. wire idempotent historical backfill in `cog_load()`;
8. register cog in `_CORE_COGS`;
9. implement Discord summary + chart;
10. clarify `..history` help;
11. focused tests;
12. full validation;
13. write durable packet summary.

## Acceptance criteria

- [ ] `..performance`, `..perf`, and `..growth` are available.
- [ ] default window is 30D.
- [ ] 1D, 7D, 30D, 90D, YTD, 1Y, and all-time are supported.
- [ ] current total value is shown.
- [ ] recent growth is shown in dollars and percentage when comparison data exists.
- [ ] historical chart is generated.
- [ ] account nickname/ID and broker filtering work.
- [ ] historical backfill is attempted automatically and idempotently.
- [ ] historical portfolio points aggregate account-specific backfill rows correctly by date.
- [ ] changed account coverage cannot silently appear as growth.
- [ ] valuation basis is disclosed, including mixed-basis comparisons.
- [ ] existing `..history` remains quantity history.
- [ ] user-facing output does not call balance growth an investment return.
- [ ] no new schema migration is introduced unless required by a verified blocker.
- [ ] durable completion summary includes the exact Authoring chat URL.

## Validation

Focused:

```bash
python -m pytest -q \
  unittests/performance_repository_test.py \
  unittests/performance_service_test.py \
  unittests/performance_cog_test.py \
  unittests/holdings_cog_test.py
```

Then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

The current accepted baseline after TP-20261004-001 is:

```text
171 passed
6 pre-existing unrelated failures
compileall clean
```

This packet must introduce **zero new failures**. Do not spend scope fixing the six unchanged unrelated failures.

## Completion report

Write:

`docs/task-packets/summaries/TP-20261004-002-SUMMARY.md`

Include:

1. command syntax and aliases;
2. supported windows;
3. account/broker scope rules;
4. observation grouping rule;
5. comparison-boundary rule;
6. common-account coverage rule;
7. mixed-basis behavior;
8. production historical backfill result;
9. historical data earliest/newest dates after backfill;
10. chart/downsampling behavior;
11. focused/full validation;
12. any future true-return/benchmark recommendation.

Required backlink:

```text
Authoring chat: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e
```

## Next Handoff

Expected next packet:

`TP-20261003-012 — Parsing and Runtime Cleanup`

After TP-002 lands:

- next packet state: refresh-required;
- ChatGPT/user planning refresh required: yes;
- refresh TP-012 against the final persistence/service/cog layout before implementation;
- use this exact authoring chat:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e
