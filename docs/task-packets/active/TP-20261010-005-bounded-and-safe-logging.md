# TP-20261010-005: Bound Logging Memory, Disk Churn, and Sensitive Payloads

**Packet ID:** TP-20261010-005  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-005-bounded-and-safe-logging.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** High  
**Authoring chat:** not-recorded  

## Objective

Reduce bound logging memory, disk churn, and sensitive payloads overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `utils/logging_setup.py`
- `utils/openai_utils.py`
- `utils/holdings_importer.py`
- `rsassistant/bot/core.py`
- `rsassistant/bot/tasks.py`
- `unittests/logging_setup_test.py (new)`
- `unittests/openai_utils_test.py`
- `config/.env.example`

## Confirmed current behavior

`TimeLengthListDuplicateFilter.logged_messages` keeps hashes indefinitely; it formats every message and truncates to 200 characters before handlers. `utils/openai_utils.extract_reverse_split_details` logs the entire system/user prompts and raw response at INFO, including source notice text. Routine importer and command messages also log at INFO. Logs are emitted both to `app.log` and stdout/Docker json logs.

## Required changes and implementation order

1. Make dedupe storage bounded by time AND count, e.g. `OrderedDict` with a default 1,024 unique keys and 60-second expiry. Evict expired keys opportunistically; never suppress WARNING/ERROR/CRITICAL, financial/order/audit events, or tagged `never_dedupe`. Hash normalized message only after level filtering.
2. Preserve complete failure diagnostics where safe; remove unconditional 200-character truncation of critical diagnostic records. Never log full prompts, raw LLM outputs, credentials, account numbers, or full command bodies; report call ID, model, text length, ticker, duration, HTTP status, error class only.
3. Decrease routine no-change imports and self-message handling to DEBUG; retain event-based INFO entries for actual imports, dispatched orders, startup, shutdown, and failures.
4. Keep logfile rotation bounded as now; explain tradeoff of stdout duplicate output and Docker json-file rotation. Honor existing configured LOG_LEVEL/LOG_FILE/LOG_BACKUP_COUNT if supported and document defaults, rather than silently ignoring env settings.
5. Ensure `setup_logging()` is idempotent and filter implementation does not recursively emit logs or mutate record.levelname across handlers.

## Focused tests and validation

Repeated unique-message stress test must keep dedupe count bounded, warnings survive, logs never include injected prompt secrets, output appears in file and console with stable formatting, and no recursion. `python -m pytest -q unittests/logging_setup_test.py unittests/openai_utils_test.py`.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] Bounded log dedupe memory; no full LLM prompts at INFO; low-value unchanged-input logs eliminated; warnings preserved.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-005-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No new telemetry backend, secret redaction claims without tests, or removal of order-audit trails.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
