# Task Packet Tracker

Live execution ledger for canonical RSAssistant task packets.

Controlled statuses and lifecycle rules are defined in [README.md](README.md).

## Active packets

No canonical active packets are currently registered.

## Historical / re-baseline queue

| Packet ID | Title | Status | Reason | Next action | Packet |
| --- | --- | --- | --- | --- | --- |
| TP-20260612-001 | Legacy RSAssistant Hardening Train (00–09) | Superseded | Packet assumptions no longer match current main; persistence packets 06/07 are visibly unimplemented and the train predates later repo changes. | Re-decompose against current main; reuse valid requirements selectively. | [wrapper](archived/TP-20260612-001-legacy-rsassistant-hardening-train.md) |

## Current modernization facts to preserve during re-baseline

- SQL/SQLite is already authoritative for several domains, including account mappings, watchlists/sell lists, order history, and reverse-split persistence.
- Excel writes are hard-disabled, but `utils/excel_utils.py`, `openpyxl`, Excel config, and Docker volume/runtime directories remain.
- `utils/order_queue_manager.py` still uses `volumes/db/order_queue.json`.
- `utils/order_send_log_manager.py` still uses `volumes/db/order_send_log.json`.
- `utils/split_watch_utils.py` still uses a module-level JSON-backed watchlist.
- Holdings ingestion writes SQL, but operational reads still heavily depend on `volumes/logs/holdings_log.csv`.
- `utils/runtime_db.py` does not exist on current main.
- The old hardening packets 06/07 describe useful target schemas but were not implemented.

## Blockers

None. The next step is deliberate decomposition, not running the legacy train.
