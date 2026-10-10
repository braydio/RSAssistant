# TP-20261010-009: Stop Shipping Runtime Artifacts and Add Safe Retention

**Packet ID:** TP-20261010-009  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-009-artifact-hygiene-and-retention.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** Normal  
**Authoring chat:** not-recorded  

## Objective

Reduce stop shipping runtime artifacts and add safe retention overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `.gitignore`
- `.dockerignore`
- `docs/architecture.md`
- `scripts/audit_runtime_artifacts.py (new)`
- `unittests/runtime_artifacts_test.py (new)`
- `volumes/archive/docker-logs-legacy/ (tracked legacy data)`
- `volumes/db/fidelity_errors/ (tracked error captures)`

## Confirmed current behavior

The tracked repository tree contains `volumes/archive/docker-logs-legacy/app.log.1` (~10 MB), multiple `volumes/db/fidelity_errors/*.html` captures (~3.9-4.4 MB each), PNGs, and an XLSX example. `.gitignore` excludes generic `*.log` but not already-tracked files or HTML captures. `.dockerignore` presently omits most runtime volumes.

## Required changes and implementation order

1. Add explicit `volumes/**` runtime-data exclusions with narrow allowlists for small documentation and genuinely synthetic fixtures. Preserve `volumes/db/README.md` and justified sample assets; do not leak .env/credentials via Docker context.
2. Write `scripts/audit_runtime_artifacts.py` as a dry-run-first inventory of artifact counts, bytes, age, and optional retention candidates under `VOLUMES_DIR` (logs/cache/debug HTML/PNG only). Never delete SQL databases, WAL files, holdings/order audit trails, source docs, or operator-created backups.
3. Provide explicit opt-in `--prune --older-than-days N` limited to known expendable error capture and rotated debug files, path-constrained below VOLUMES_DIR, no symlink traversal, printed item-by-item report. Dry run must not mutate.
4. In a separate implementation commit or explicitly reviewed step, untrack legacy binary/debug artifacts using `git rm --cached` after inventory and operator approval; do not rewrite Git history and do not delete local user-owned captures. Document clone size before/after and archival decision.
5. Introduce a stable error-capture retention setting if the producer actually emits to `volumes/db/fidelity_errors`; otherwise avoid inventing one.

## Focused tests and validation

Tempdir synthetic fixtures, path traversal/symlink protection, dry-run no-change, prune scope, protected DB and order log. `python -m pytest -q unittests/runtime_artifacts_test.py`; `git ls-files volumes` documented in closeout.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] Safe, auditable cleanup path and no future accidental commits/build copies of mutable runtime data; old debug artifacts remain untouched until explicitly reviewed.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-009-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No automatic deletion of business/trade records or `git filter-repo` history surgery.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
