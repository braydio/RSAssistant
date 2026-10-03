# Task Packet System

This directory is the canonical home for executable implementation task packets in RSAssistant.

Do not create new executable packets under arbitrary docs folders or inside legacy workstream directories. Historical packet trains may remain in place for context, but only packets registered in `INDEX.md` and `TRACKER.md` are executable.

## Canonical layout

```text
docs/task-packets/
├── README.md
├── INDEX.md
├── TRACKER.md
├── active/
│   └── TP-YYYYMMDD-NNN-kebab-case-slug.md
├── completed/
│   └── TP-YYYYMMDD-NNN-kebab-case-slug.md
├── archived/
│   └── TP-YYYYMMDD-NNN-kebab-case-slug.md
└── rsassistant-hardening/
    └── ... legacy pre-canonical packet train ...
```

Lifecycle folders:

- `active/`: Draft, Ready, In Progress, or Blocked.
- `completed/`: implemented and validated.
- `archived/`: Superseded, Cancelled, or historical wrapper packets.

Do not duplicate one canonical packet across lifecycle folders.

## Packet naming

Every canonical packet receives an immutable ID:

```text
TP-YYYYMMDD-NNN
```

Filename:

```text
TP-YYYYMMDD-NNN-kebab-case-slug.md
```

Rules:

- `YYYYMMDD` is the packet creation date.
- `NNN` starts at `001` and increments when multiple packets are created on the same date.
- Never reuse an old Packet ID.
- The Packet ID never changes when the packet moves between lifecycle folders.
- The filename should use the same Packet ID plus a short descriptive slug.

## Controlled statuses

Use exactly one:

- `Draft`
- `Ready`
- `In Progress`
- `Blocked`
- `Complete`
- `Superseded`
- `Cancelled`

Folder and status must agree:

| Status | Folder |
| --- | --- |
| Draft | active |
| Ready | active |
| In Progress | active |
| Blocked | active |
| Complete | completed |
| Superseded | archived |
| Cancelled | archived |

## Required packet header

```markdown
# TP-YYYYMMDD-NNN: Human-readable title

**Packet ID:** TP-YYYYMMDD-NNN
**Status:** Ready
**Created:** YYYY-MM-DD
**Last updated:** YYYY-MM-DD
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/active/TP-...`
**Workstream size:** One implementation packet
**Depends on:** None
```

Add Priority only when ordering materially matters.

## Agent execution flow

1. Read root `AGENTS.md`.
2. Read this file.
3. Read `TRACKER.md`.
4. Resolve the assigned Packet ID through `INDEX.md`.
5. Open only the canonical packet path.
6. Confirm its status is executable.
7. Validate only the packet's named files/symbols against current `main`.
8. Do not perform a repo-wide rediscovery pass unless the packet is demonstrably stale.
9. Mark the packet and tracker `In Progress` when implementation starts.
10. Implement in packet order and stay inside its non-goals.
11. Run focused tests first, then full/completion validation.
12. Record exact blockers or deviations rather than silently weakening requirements.
13. On completion:
    - set Status to `Complete`;
    - update Last updated;
    - move the packet to `completed/`;
    - update `INDEX.md` and `TRACKER.md` in the same change.
14. If superseded/cancelled, move it to `archived/` and identify the replacement Packet ID when applicable.

Legacy packet files under `docs/task-packets/rsassistant-hardening/` are not executable unless a new canonical packet explicitly adopts or replaces their requirements.

## TRACKER vs INDEX

`INDEX.md` answers: **what packets exist and where are they?**

`TRACKER.md` answers: **what is active, what is blocked, what depends on what, and what should run next?**

Update both whenever a canonical packet is created, moved, completed, blocked, superseded, or cancelled.

## Authoring standard

Task packets are executable interfaces, not brainstorming notes.

Before writing one:

1. Inspect current `main`.
2. Identify the exact files, functions, classes, routes, cogs, handlers, storage tables, config keys, and tests involved.
3. Separate confirmed current behavior from recommended changes.
4. Resolve architecture questions before handoff when repository evidence is sufficient.

A strong packet includes, when applicable:

- exact repository-relative file paths;
- exact function/class/cog/handler names;
- current code excerpts around the seam being changed;
- concrete replacement code or pseudocode when practical;
- SQLite schema/queries and migration behavior for persistence changes;
- compatibility requirements for public helper APIs;
- implementation order;
- focused tests and exact validation commands;
- acceptance criteria;
- explicit non-goals;
- dependencies/locks;
- expected completion report;
- expected packet count and order when work is split.

### Minimize token burn and drift

Prefer:

```text
File: utils/order_queue_manager.py
Functions: add_to_order_queue(), get_order_queue()

Current:
    JSON file is authoritative.

Target:
    SQLite repository owns state while returned dict shape remains unchanged.

Recommended query:
    INSERT INTO scheduled_orders (...)
    VALUES (...)
    ON CONFLICT(order_id) DO UPDATE ...
```

over:

```text
Find the relevant persistence code and migrate it to SQL.
```

Additional rules:

- Put exact paths before prose.
- Use symbols as primary anchors; line numbers are optional hints only.
- Include real code recommendations when the intended shape is known.
- Reuse existing helpers/contracts instead of inventing parallel systems.
- State `Do not rediscover` boundaries when the relevant surface has already been traced.
- Do not push product/architecture decisions onto the implementing agent when the packet author can settle them first.
- Do not combine unrelated cleanup with a persistence packet.
- One packet should be one coherent, independently testable workstream.
- Split packets at persistence-authority changes, runtime safety boundaries, or independently shippable contracts.
- When runtime evidence changes the diagnosis, update the canonical packet directly and bump `Last updated`.
- If a recommendation remains uncertain, name the exact file/symbol/query that must be verified.

## RSAssistant persistence rule for new packets

Prefer one authoritative operational state store per domain.

Current modernization direction:

- SQLite under `VOLUMES_DIR/db/` should own mutable runtime/domain state.
- CSV may remain an import/export, operator-readable snapshot, or audit artifact, but should not be a second authoritative write/read path.
- JSON files may be accepted as one-time legacy migration inputs, but new runtime mutation should not depend on whole-file rewrites.
- Excel is legacy historical material only and should not regain runtime authority.
- Config belongs in `config/` / environment variables, not in runtime state tables.
- Discord I/O/orchestration belongs in `rsassistant/`; reusable persistence/domain helpers should not depend on Discord contexts.

Any packet intentionally violating one of these rules must state why.

## Lightweight template

```markdown
# TP-YYYYMMDD-NNN: Title

<header>

## Objective
One concrete outcome.

## Confirmed current state
Exact files/symbols and current behavior.

## Required changes
### 1. path/to/file
Current seam, target behavior, recommended code.

## Tests
Exact files/cases/commands.

## Non-goals
Explicit boundaries.

## Implementation order
1. ...
2. ...

## Acceptance criteria
- [ ] ...

## Completion report
Files changed, contracts implemented, tests, deviations.
```
