# TP-20261010-004: Make Holdings Snapshot Import Change-Driven and Retry-Safe

**Packet ID:** TP-20261010-004  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-004-holdings-import-change-detection.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** High  
**Authoring chat:** not-recorded  

## Objective

Reduce make holdings snapshot import change-driven and retry-safe overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `utils/holdings_importer.py`
- `rsassistant/bot/tasks.py`
- `rsassistant/bot/cogs/holdings.py`
- `unittests/holdings_importer_test.py (new)`
- `config/.env.example`

## Confirmed current behavior

`import_holdings_if_updated()` logs multiple INFO messages on every 5-minute check; uses `Path.stat().st_mtime` and a process-local `_last_import_mtime`; after calling `import_holdings_file()` it advances the last mtime even when parsing failed or zero valid rows were accepted. This can permanently suppress retry until a later file rewrite.

## Required changes and implementation order

1. Replace mtime float with a tuple of `(st_mtime_ns, st_size)`; acknowledge only after successful schema validation AND persistence. Do not equate a zero-row/failed import with success; provide internal explicit outcome `changed/skipped/failed` without breaking public return type `int`.
2. Check a stable snapshot: stat before and after reading, and reject/retry on size or mtime change to avoid importing a partially written shared file. On failure retain the previous accepted fingerprint.
3. Preserve `import_holdings_file(path)->int` and `import_holdings_if_updated(path)->int` compatibility; catch *only* expected I/O/JSON/schema errors, and ensure failed CSV/SQL write never advances fingerprint.
4. For unchanged snapshot, emit DEBUG at most or no line. Warn about missing file only on state transition or a bounded interval, not every poll. Disable checking entirely through scheduler when `AUTO_RSA_HOLDINGS_ENABLED=false`.
5. The existing SQL/CSV writes and staged-refresh contract remain authoritative for this packet. When TP-006/007 lands, reconcile this adapter to new importer without reintroducing CSV authority.

## Focused tests and validation

Write tempfile tests: unchanged snapshot; equal-mtime changed-size; invalid JSON corrected without mtime advancement; write failure retry; file changed during read; missing->present transition; disabled mode; repeated import does not duplicate entries. `python -m pytest -q unittests/holdings_importer_test.py unittests/csv_utils_test.py`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] No redundant import or informational log on an unchanged file and no dropped retry after a failed import. Existing caller return type stable.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-004-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No watchdog dependency, broker polling change, or holdings schema migration.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
