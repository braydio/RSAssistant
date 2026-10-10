# TP-20261003-007: Make SQLite the Operational Holdings Read Source

**Packet ID:** TP-20261003-007
**Status:** Complete
**Created:** 2026-10-03
**Last updated:** 2026-10-03
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/completed/TP-20261003-007-holdings-authority-inversion.md`
**Workstream size:** One implementation packet
**Depends on:** TP-20261003-006

## Goal

Make `holdings_current` the only operational source for holdings reads. Keep public/domain row shapes stable at the repository boundary. CSV may be exported for compatibility, and disabling CSV export must not break holdings commands.

## Exact seams

- `rsassistant/persistence/holdings.py`: add domain queries for current rows, freshness, clearing, and ticker presence/recent history (use current snapshot timestamps; do not consult CSV).
- `utils/holdings_snapshot.py`, `utils/audit_watchlist_utils.py`: replace `load_csv_log` / direct CSV reads with SQL rows.
- `utils/csv_utils.py`: migrate `is_ticker_currently_held`, `was_ticker_held_recently`, `get_top_holdings`, `sell_all_position`, refresh begin/finalize/abort, save/export, and clear. Preserve returned row dictionaries and command behavior.
- `utils/utility_utils.py`: migrate `check_holdings_timestamp`, `track_ticker_summary`, `get_account_totals`, and `all_brokers_summary_by_owner` to SQL. Keep `holding_logs_file` accepted for call compatibility but ignore it for operational data.
- Add/update focused tests in `unittests/holdings_repository_test.py`, `unittests/csv_utils_test.py`, `unittests/utility_utils_test.py`, `unittests/holdings_cog_test.py`, and snapshot/audit tests as appropriate.

## Required behavior

1. Incoming full snapshots validate and commit to SQL even when `CSV_LOGGING_ENABLED=False`.
2. Refresh staging works without a `.next` file. SQL staging is activated atomically at refresh completion and discarded on abort; optional CSV promotion/export follows SQL publication.
3. Any SQL or input validation failure leaves the prior current snapshot intact. CSV export failure must not roll back committed SQL state.
4. Map SQL fields to existing CSV-style row keys only at utility compatibility boundaries (`Broker Name`, `Broker Number`, `Account Number`, `Stock`, `Quantity`, `Price`, `Position Value`, `Account Total`, `Timestamp`).
5. Include zero and negative positions for current snapshot reads where domain logic needs them. Positive-only historical `HoldingsLive` behavior remains unchanged.
6. Preserve `get_top_holdings()` return tuple, broker/ticker grouping, quantity threshold, and footer timestamp. Preserve `sell_all_position()` brokerage filter and minimum quantity across accounts.
7. Holdings clear command clears SQL current state regardless of CSV export setting.
8. `track_ticker_summary()` continues configured-account mapping behavior and returns the same `(statuses, timestamp)` shape when `collect=True`.

## Implementation order

1. Add focused SQL query/clear helpers and tests.
2. Convert read-only consumers and compatibility mapping.
3. Decouple refresh staging and SQL publication from CSV file presence/configuration.
4. Run targeted tests, full unittest discovery, and compileall.

## Non-goals

- Do not change `HoldingsLive` historical-feed retention or remove its CSV output.
- Do not migrate order history or split-monitor CSV in this packet.
- Do not alter Discord command wording except where disabled CSV previously caused a broken command.

## Validation

```bash
python -m pytest -q unittests/csv_utils_test.py unittests/utility_utils_test.py unittests/holdings_cog_test.py unittests/holdings_repository_test.py
python -m unittest discover -s unittests -p '*_test.py'
python -m compileall .
```

## Acceptance criteria

- Operational holdings readers succeed with no holdings CSV present and with CSV export disabled.
- Reads reflect only `holdings_current`; refresh staging is invisible until activation.
- SQL state remains authoritative if compatibility export fails.
- Targeted and full repository validation pass.
