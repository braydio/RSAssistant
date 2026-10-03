# TP-20260612-001: Legacy RSAssistant Hardening Train (00–09)

**Packet ID:** TP-20260612-001  
**Status:** Superseded  
**Created:** 2026-06-12  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** historical  
**Canonical path:** `docs/task-packets/archived/TP-20260612-001-legacy-rsassistant-hardening-train.md`  
**Workstream size:** Historical wrapper  
**Depends on:** None  

## Purpose

This wrapper records the pre-canonical hardening train under:

    docs/task-packets/rsassistant-hardening/

The original workstream contains packets 00 through 09 and a `MANIFEST.md`. It remains useful design history, especially:

- Packet 06: order queue / sent-order runtime persistence to SQLite.
- Packet 07: split monitor persistence to SQLite.
- Packet 08: async runtime cleanup.
- Packet 09: Excel retirement, dependency pruning, and runtime cleanup.

## Why it is superseded

Do not run the old sequence directly against current `main`.

Confirmed current-main evidence shows that assumptions in the old train are stale or incomplete:

- `utils/runtime_db.py` still does not exist.
- order queue and sent-order audit remain JSON-backed.
- split monitor remains module-level JSON-backed state.
- Excel is deprecated/hard-disabled but still shipped through code, dependency, config, Docker volume, and startup directory creation.
- holdings remain a dual SQL + CSV path, with several production reads still using CSV.
- later repository changes landed after the workstream baseline.

The correct next move is to re-decompose modernization around current persistence authority and module boundaries rather than checking boxes in the historical manifest.

## Historical source

See:

    docs/task-packets/rsassistant-hardening/MANIFEST.md
    docs/task-packets/rsassistant-hardening/00-ci-foundation.md
    ...
    docs/task-packets/rsassistant-hardening/09-runtime-cleanup.md

Use those files as implementation references only. Requirements must be copied into new canonical packets before execution.
