# Repository Guidelines

## Task Packet System (Authoritative)

Executable implementation packets live under `docs/task-packets/`.

Canonical control files:

- `docs/task-packets/README.md` – hardened naming, lifecycle, execution, persistence, and authoring rules.
- `docs/task-packets/INDEX.md` – canonical discovery catalog.
- `docs/task-packets/TRACKER.md` – live status, priority, dependencies, and blockers.
- `docs/task-packets/active/` – Draft, Ready, In Progress, and Blocked packets.
- `docs/task-packets/completed/` – Complete packets.
- `docs/task-packets/archived/` – Superseded and Cancelled packets.
- `docs/task-packets/summaries/` – durable implementation/refresh closeout summaries keyed by Packet ID.

Canonical filenames use:

```text
TP-YYYYMMDD-NNN-kebab-case-slug.md
```

The old `docs/task-packets/rsassistant-hardening/` train is pre-canonical design history. Do not execute it directly. Its historical wrapper is `TP-20260612-001`; copy still-valid requirements into new canonical packets before implementation.

### Agent execution flow

When asked to implement or continue a packet:

1. Read this `AGENTS.md`.
2. Read `docs/task-packets/README.md`.
3. Check `docs/task-packets/TRACKER.md`.
4. Resolve the Packet ID through `docs/task-packets/INDEX.md`.
5. Open only the canonical packet.
6. Validate named files/symbols against current `main`, without a repo-wide rediscovery pass unless the packet is stale.
7. Mark packet + tracker `In Progress` when work starts.
8. Follow implementation order, compatibility requirements, non-goals, tests, and acceptance criteria.
9. Record exact blockers/deviations instead of weakening requirements silently.
10. On completion, move the packet to `completed/` and update index/tracker in the same change.

### Packet is the brief

When the user names a Packet ID, packet title, or clearly recognizable packeted workstream, resolve and read the canonical packet before implementation. Treat that packet as the complete brief; do not ask the user to restate requirements already present there.

Current-turn user instructions may narrow, pause, or explicitly override packet details. Otherwise preserve the packet's objective, non-goals, acceptance criteria, validation, dependency/refresh gates, and handoff requirements.

If the packet is stale relative to current `main`, refresh the packet first rather than silently improvising around drift.

### Authoring chat backlinks

When a task packet contains an `Authoring chat:` or `Refresh planning chat:` URL:

- copy the exact URL verbatim into every durable packet completion/recovery/refresh summary;
- include the same exact URL in the final user-facing completion or refresh-required response;
- never shorten, redirect, normalize, or replace it with a generic ChatGPT/project link;
- never infer or invent a conversation URL;
- when the user supplies a conversation URL while authoring or refreshing a packet, add it to that packet's metadata immediately.

The backlink exists so the next planning/review pass can return to the exact conversation that authored the packet.

### Durable packet summaries

Every implemented canonical packet writes one durable closeout file:

```text
docs/task-packets/summaries/<PACKET-ID>-SUMMARY.md
```

Use one file per Packet ID. Update/overwrite that file as the same packet advances; do not create duplicate summaries for the same packet. Commit the summary with the implementation whenever practical.

Required summary shape:

```markdown
# <PACKET-ID> Completion Summary

Authoring chat: <exact packet URL | not-recorded>

## Outcome
- Status: success | partial | blocked
- What changed: ...
- Files changed: ...

## Validation
- <command>: passed | failed | not-run
- ...

## Process Feedback
- Friction severity: none | low | medium | high
- What went wrong: none | ...
- Root cause / contributing factors: none | ...
- Tooling / docs drift discovered: none | ...
- Follow-up: none | fixed-in-scope | <Packet ID> | manual-follow-up

## Next Handoff
- Next packet: <Packet ID | none>
- Next packet state: ready | dependency-gated | refresh-required | human-required | none
- ChatGPT/user planning refresh required: yes | no
- Authoring chat: <exact packet URL | not-recorded>
- Refresh reason: none | ...
- Next action: ...
- Blockers or open questions: none | ...
```

Keep the summary factual. Record awkward parts, failed checks, stale assumptions, or follow-up debt rather than writing a victory note that merely repeats the diff.

### User-facing closeout format

For a completed packet, keep the final response concise and include:

```text
PACKET COMPLETE
Packet: <Packet ID — title>
Summary: <one-sentence result>
Validation: <focused/full result>
Persistent summary: docs/task-packets/summaries/<PACKET-ID>-SUMMARY.md
Next: <next Packet ID/state/action>
Authoring chat: <exact URL when recorded>
```

When a dependency or packet requires return to ChatGPT/user planning before implementation continues, do not dump a long terminal recap. Use:

```text
PLANNING REFRESH REQUIRED
Packet: <Packet ID>
Persistent summary: docs/task-packets/summaries/<PACKET-ID>-SUMMARY.md
Reason: <specific drift/decision>
Authoring chat: <exact recorded URL>
Next action: review/refresh the named successor against current main
```

The durable summary carries the implementation detail; the chat response is the navigation card.

### Task packet authoring rules

These rules apply to ChatGPT, Codex, and any other agent writing packets:

- Inspect current `main` first.
- Give exact repository-relative file paths.
- Name exact functions, classes, cogs, handlers, tables, config keys, and tests.
- Include current snippets and concrete target code/pseudocode when practical.
- For persistence changes, specify exact table shape, transaction boundaries, migration behavior, idempotency, and compatibility surfaces.
- Prefer symbols over line numbers; line numbers are only hints.
- Reuse existing helpers and public APIs instead of building parallel systems.
- State `Do not rediscover` boundaries when the relevant code path has already been traced.
- Include implementation order, focused tests, validation commands, acceptance criteria, non-goals, dependencies, and completion-report requirements.
- State expected packet count/order when decomposing a larger roadmap.
- Keep each packet independently testable and bounded to one coherent workstream.
- Minimize token burn by supplying real file paths and real code recommendations rather than telling the implementer to search broadly.
- When new runtime evidence changes the diagnosis, update the canonical packet and tracker directly.
- When the user provides a ChatGPT planning/review URL, record it exactly as `Authoring chat:` in the packet; use `Refresh planning chat:` too when a later dependency refresh must return to that conversation.

### Persistence modernization rule

For new work, avoid multiple authoritative stores for the same domain.

- SQLite under `VOLUMES_DIR/db/` should own mutable runtime/domain state.
- CSV is acceptable as import/export, audit, or operator-readable snapshot output, but should not remain the authoritative operational read/write store once a SQL domain is migrated.
- JSON files are acceptable as one-time legacy migration inputs, not as new whole-file runtime databases.
- Excel is historical/legacy only and must not regain runtime authority.
- Configuration remains in environment/`config/`, separate from mutable runtime state.
- Discord orchestration belongs in `rsassistant/`; persistence/domain helpers should not require Discord contexts.

## Project Structure & Modules
- `RSAssistant.py`: main entrypoint for the assistant/bot.
- `rsassistant/`: Discord runtime (cogs, tasks, handlers).
- `utils/`: shared helpers (parsing, scheduling, persistence, I/O).
- `plugins/`: optional extensions loaded via `ENABLED_PLUGINS`.
- `externalization-staging/`: experimental utilities slated for extraction.
- `config/`: single source for settings and `.env` templates.
- `docs/`: operator and architecture documentation.
- `unittests/`: unit tests grouped by feature (pattern `*_test.py`).
- `volumes/`: Docker-mounted db/logs data (never commit).
- Docker: `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`.

## Build, Test, and Dev Commands
- Setup venv: `python -m venv .venv && source .venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Run app: `python RSAssistant.py`
- Run PR watcher: `python externalization-staging/devops/pr_watcher.py`
- Run tests: `python -m unittest discover -s unittests -p '*_test.py'`
- Docker build/run: `docker build -t rsassistant .` then `docker compose up`

## Coding Style & Naming
- Python, PEP 8, 4-space indentation; prefer type hints where reasonable.
- Names: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_CASE`.
- Keep functions focused; avoid side effects in utilities.
- Logging via `utils/logging_setup.py`; favor structured, redaction-safe logs.
- Module boundaries: keep Discord I/O in `rsassistant/`, helpers in `utils/`.

## Documentation Guidelines
- Always update the /config/.env.example or similar with any configuration updates.
- Keep `README.md` focused on setup, config, and operator workflows.
- Keep architecture notes in `docs/architecture.md`.
- Prune stale docs instead of accumulating duplicates.

## Testing Guidelines
- Framework: `unittest` (tests in `unittests/`, pattern `*_test.py`).
- Add tests for new features and bug fixes; cover edge cases and I/O boundaries.
- Use deterministic inputs; avoid real network or live broker calls.
- Example: `python -m unittest unittests/order_queue_manager_test.py`.

## Commit & Pull Requests
- Commits: prefer Conventional Commits (e.g., `feat(config): support custom volumes directory`).
- If Conventional Commits are not used, use clear imperative messages.
- PRs: concise description, link issues, list changes, screenshots/logs for user-visible behavior.
- Required: tests passing, updated docs (README or examples) for user-facing changes.

## Security & Configuration
- Never commit secrets. Copy `config/.env.example` to `config/.env` for local dev.
- Primary app settings: `config/.env` (with `ENV_FILE` overrides). `config/settings.yml` is legacy/compat.
- Redact tokens and account identifiers in logs and PRs.

## Conventions & Examples
- New util: `utils/my_feature_utils.py` with focused functions + tests in `unittests/my_feature_utils_test.py`.
- CLI run with custom config: `ENV_FILE=config/.env python RSAssistant.py`.
- After adding a feature, increment the version in `config/settings.yml`.


## Legacy Hardening Workstream

The historical `docs/task-packets/rsassistant-hardening/00-09` train is preserved for implementation ideas but is no longer an executable source of truth. Its baseline predates current main and several persistence assumptions remain unimplemented.

Do not run `scripts/run-rsassistant-hardening.sh` against current main unless a new canonical packet explicitly reactivates and rebases that runner. Use `docs/task-packets/TRACKER.md` for current work.
