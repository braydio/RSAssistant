# TP-20261003-007: Holdings Authority Inversion

**Packet ID:** TP-20261003-007  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-007-holdings-authority-inversion.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-006  
**Priority:** High  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-006 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-006's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-006 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Make the new SQL holdings contract the operational read authority. CSV becomes optional export/audit output.

## Required call-site migration

Re-open current main and inventory these exact known readers first:

- `utils/holdings_snapshot.py`
- `utils/audit_watchlist_utils.py`
- `utils/csv_utils.get_top_holdings()`
- `utils/csv_utils.sell_all_position()`
- `rsassistant/bot/cogs/holdings.py`
- `utils/utility_utils.py` freshness/timestamp helpers
- any remaining production `HOLDINGS_LOG_CSV` reads

Use search only for `HOLDINGS_LOG_CSV`, `load_csv_log(...holdings...)`, and direct holdings CSV opens. Do not broad-audit unrelated persistence.

## Repository read API

Packet 006 should expose or be extended with read functions such as:

```python
list_current_holdings(
    broker: str | None = None,
    ticker: str | None = None,
) -> list[Holding]

list_broker_positions(...)
get_latest_observed_at(...)
is_ticker_held(...)
```

At adapter boundaries, return the dict shape callers need. Keep SQL column names out of Discord cogs.

## Writer inversion

Target flow:

```text
incoming Discord/JSON holdings snapshot
 -> normalize/validate
 -> SQL staging
 -> atomic commit to holdings_current
 -> optional CSV export generated from committed SQL
```

Delete the architectural flow where SQL is written only as a side effect of `save_holdings_to_csv()`.

Recommended refactor:

- create a domain-oriented `persist_holdings_snapshot()`;
- let CSV export be `export_holdings_csv()`;
- keep `save_holdings_to_csv()` temporarily as compatibility wrapper if callers remain, but make it delegate to SQL-first flow.

## CSV behavior

`CSV_LOGGING_ENABLED=false` must disable only CSV output. It must **not** prevent holdings refresh or holdings commands.

`clear_holdings_log()` should be renamed/deprecated or redefined carefully. Do not let a command intended to clear an export accidentally clear SQL domain state unless its user-facing semantics clearly mean “clear holdings state.” Preserve current command behavior via explicit tests.

## Specific reader behavior

### `utils/holdings_snapshot.py`

Replace:

```python
rows = load_csv_log(HOLDINGS_LOG_CSV)
```

with repository query + adapter.

### `utils/audit_watchlist_utils.py`

Use SQL current positions, not filesystem presence.

### `get_top_holdings()`

Compute from SQL current positions and repository timestamps.

### `sell_all_position()`

Query current positions by broker from SQL. Preserve its “minimum quantity per ticker across accounts” behavior unless existing tests/docs say otherwise.

## Tests

Add/update:

- holdings snapshot render from SQL with CSV missing;
- audit watchlist from SQL;
- top holdings from SQL;
- sell-all from SQL;
- CSV export disabled but commands still work;
- negative holdings survive read path;
- import/refresh -> SQL -> reader end-to-end;
- stale CSV cannot override newer SQL.

## Non-goals

- no Excel cleanup yet;
- no broad csv_utils decomposition;
- no change to trading decisions or sell semantics;
- no HistoricalHoldings redesign.

## Acceptance criteria

- [ ] zero production holdings decisions depend on reading `holdings_log.csv`.
- [ ] SQL is the holdings authority.
- [ ] CSV is optional output/import compatibility only.
- [ ] disabling CSV logging does not break holdings refresh/reporting.
- [ ] stale/missing CSV cannot alter operational holdings behavior.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report every migrated `HOLDINGS_LOG_CSV` production reader, any remaining CSV usage and why, end-to-end tests, and refresh changes.