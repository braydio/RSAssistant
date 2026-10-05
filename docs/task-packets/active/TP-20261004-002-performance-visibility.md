# TP-20261004-002: Performance Visibility and Growth History

**Packet ID:** TP-20261004-002  
**Status:** Draft  
**Created:** 2026-10-04  
**Last updated:** 2026-10-04  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261004-002-performance-visibility.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-007, TP-20261004-001  
**Priority:** High  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet is pre-authored before both the authoritative holdings reader migration and performance-history capture land.

Before implementation, inspect TP-20261003-007 and TP-20261004-001 on current main. Refresh all repository/API/schema names and actual history coverage.

If anything material changed, stop and call it out here:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff:

> Holdings authority + performance history are now implemented. The pre-authored Performance Visibility packet needs its final refresh against the landed APIs/data coverage before implementation: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

## Objective

Give the operator immediate visibility into:

- current total value;
- recent value growth;
- historical value trajectory;
- account/broker contributions to total value;
- data coverage and valuation basis.

The primary surface is Discord because RSAssistant is Discord-operated.

## Metric semantics

User-facing language must distinguish:

### Value growth

Valid now:

```text
Current value
$ change
% value change
positions value
reported account value
```

### Investment return

Do not claim this yet.

Deposits and withdrawals are not reliably modeled, so:

```text
+$500 (+4.2%) value change
```

is valid.

```text
+4.2% investment return
```

is not valid unless a future cash-flow-adjusted performance model exists.

## User experience

Add a command:

```text
..performance [window] [account-or-broker]
```

Aliases:

```text
..perf
..growth
```

Suggested windows:

- `1d`
- `7d`
- `30d`
- `90d`
- `ytd`
- `1y`
- `all`

Default: `30d`.

Examples:

```text
..performance
..performance 7d
..performance ytd
..performance 30d Fidelity
..performance all Account 2
```

Use existing account nickname/broker resolution helpers rather than create a second identity parser.

## Summary output

The Discord response should provide a compact summary before the chart.

Example shape:

```text
Portfolio Performance · 30D

Current value        $12,842.17
30D value change       +$914.28
30D change                +7.66%
7D value change        +$221.42
Since tracking        +$2,418.03

Coverage
Sep 4, 2026 → Oct 4, 2026
11 accounts · updated 8m ago

Basis
Current: reported account totals
Older history: position values where reported totals were unavailable
```

Use real values/coverage dynamically. Do not hardcode this example.

If insufficient history exists for a requested window, return `N/A` plus the earliest available observation rather than manufacturing a partial-period percentage.

## Comparison-point rules

Implement a central service, not ad hoc command math.

Recommended:

`rsassistant/services/performance.py`

Functions:

```python
get_performance_summary(window, account_ids=None, as_of=None)
get_performance_series(window, account_ids=None, as_of=None)
```

For latest:

- use newest complete snapshot for selected account scope.

For comparison boundary:

- `1d`: previous available business/observation day;
- `7d/30d/90d/1y`: nearest complete snapshot at or before the target timestamp/date;
- `ytd`: earliest complete snapshot on/after Jan 1, or nearest prior snapshot when one exists and is clearly more representative;
- `all`: earliest compatible observation.

Document the exact rule and test it.

Do not compare a complete current 11-account portfolio to a historical point containing only 6 accounts without surfacing the coverage mismatch.

## Coverage integrity

Performance summaries must be scope-aware.

Return metadata such as:

```python
{
    "account_count": 11,
    "current_observed_at": ...,
    "comparison_observed_at": ...,
    "current_coverage": [...],
    "comparison_coverage": [...],
    "basis": ...,
    "mixed_basis": True,
}
```

If account coverage differs materially between endpoints:

- calculate only common accounts by default, or
- mark the result as non-comparable and suppress the percentage.

Prefer **common-account comparison** for robust growth math, while separately reporting current total.

Do not let newly added/removed accounts masquerade as investment growth.

## Historical chart

Generate a Discord PNG line chart using matplotlib, consistent with existing history behavior.

Primary series:

- portfolio/account `effective_value`.

Optional second series when useful and available:

- `positions_value`.

Do not overload the first version with per-account lines by default.

Chart:

- requested time window;
- currency-formatted y-axis;
- concise title;
- first/latest value annotations if readable;
- basis boundary note in footer/caption when history shifts from `historical_positions_sum` to `reported_total`.

For very long `all` windows, downsample **for display only** while preserving source snapshots. Use deterministic daily/weekly/monthly rendering based on range; do not delete data.

## Account/broker breakdown

Summary should support selected scope.

For whole portfolio, include top contributors to current value and optionally largest absolute changes when data coverage supports it.

Keep to a short list, e.g. top 3, to avoid Discord-wall syndrome.

## Existing `..history`

Do not silently redefine it.

Current `..history` is a ticker/account **quantity history** command. Preserve it for now.

Update its help text to clearly say quantity history, and point users to `..performance` for value growth/history.

Later cleanup may merge UX only with an explicit design packet.

## Expected files

After refresh, likely:

- `rsassistant/services/performance.py` (new)
- `rsassistant/bot/cogs/holdings.py` or new `rsassistant/bot/cogs/performance.py`
- `rsassistant/bot/history_query.py` only for shared plotting helpers/help clarification
- performance repository from TP-20261004-001
- `utils/config_utils.py` only if a feature flag remains justified
- unit tests
- README/help docs

Prefer a separate `performance.py` cog if holdings cog would become materially more crowded.

## Feature flag

Do not default this feature off merely because old `HISTORY_QUERY_ENABLED` exists.

If the performance data contract exists and the command is safe, expose it by default. A new feature flag is unnecessary unless there is a concrete operational reason.

## Tests

Cover:

- 1d/7d/30d/90d/ytd/all boundary selection;
- positive and negative value changes;
- percentage math;
- zero starting value handling;
- insufficient history;
- common-account coverage comparison;
- newly added account does not appear as fake growth;
- removed/missing account behavior;
- mixed valuation basis disclosure;
- account filter;
- broker filter;
- chart generation;
- current value can show even with no historical comparison;
- `..history` remains quantity-focused.

## Non-goals

- no time-weighted return;
- no money-weighted/XIRR return;
- no deposit/withdrawal inference;
- no S&P 500 benchmark;
- no web dashboard;
- no P&L/tax-lot engine.

Those can become future packets once cash-flow and trade-lot data is trustworthy.

## Acceptance criteria

- [ ] operator can see current portfolio/account value.
- [ ] operator can see 1D, 7D, 30D, 90D, YTD, 1Y, and all-time value change when coverage exists.
- [ ] recent growth is shown in both dollars and percent.
- [ ] historical chart is available.
- [ ] account/broker filtering works.
- [ ] data coverage/basis is visible.
- [ ] changing account coverage cannot silently distort growth percentage.
- [ ] user-facing text says value change/growth, not investment return.

## Validation

Run focused performance command/service tests, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

## Completion report

Report:

1. command syntax/aliases;
2. supported windows;
3. comparison-boundary rule;
4. common-account/coverage rule;
5. historical data start date;
6. valuation-basis behavior;
7. chart behavior;
8. tests;
9. anything that should become a future true-return/benchmark packet.
