# TP-20261003-012: Parsing and Runtime Cleanup

**Packet ID:** TP-20261003-012  
**Status:** Draft  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-012-parsing-runtime-cleanup.md`  
**Workstream size:** One implementation packet  
**Depends on:** TP-20261003-011  
**Priority:** Normal  
**Controller:** TP-20261003-001  

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-011 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-011's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-011 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


## Objective

Finish the modernization train with bounded parser decomposition, runtime cleanup, healthcheck hardening, dependency pruning, and documentation reconciliation.

Do not use this as a grab-bag refactor. Every change must map to one of the sections below.

## 1. Decompose `utils/parsing_utils.py`

After refresh, inventory symbols and group by actual input domain.

Likely target:

```text
rsassistant/parsing/
    __init__.py
    alerts.py
    orders.py
    holdings.py
    reverse_splits.py
```

Only create modules with real cohesive symbol groups.

Keep `utils/parsing_utils.py` as temporary compatibility exports if needed.

Do not change parsing semantics while moving code.

## 2. Async/runtime cleanup

Search bounded symbols:

```text
BackgroundScheduler
threading
asyncio.to_thread
time.sleep(
requests.
full_analysis
```

Fix only blocking work reachable from active async Discord paths.

Prefer `asyncio.to_thread` for existing synchronous clients rather than rewriting network stacks.

## 3. Docker heartbeat healthcheck

Current `docker-compose.yml` historically checks only:

```yaml
test: ["CMD", "cat", "/app/volumes/logs/heartbeat.txt"]
```

Add `scripts/healthcheck.py` if this remains current.

Recommended behavior:

- resolve heartbeat path from env/default;
- fail if file missing;
- parse mtime;
- fail if older than a threshold derived from `HEARTBEAT_INTERVAL`, e.g. `max(interval * 3, 180)`;
- exit 0 only when fresh.

Update Compose to execute it.

## 4. Entrypoint permissions

If still present, remove blanket:

```sh
chmod -R 755 "$VOLUMES_DIR"
```

Create required directories/files with only necessary permissions. Do not invent host UID/GID behavior.

## 5. Dependency pruning

Before removing a dependency, prove zero production/test imports:

```bash
rg -n "\b(keyboard|selenium|webdriver_manager|numpy|rich|openpyxl)\b" .
```

`openpyxl` should already be gone from Packet 009.

Remove only proven-unused packages. Do not prune based on intuition.

## 6. Config compatibility cleanup

Search for deprecated:

- `SQL_LOGGING_ENABLED`;
- `CSV_LOGGING_ENABLED` semantics that still imply authority;
- legacy Excel keys;
- legacy settings YAML fallbacks.

Remove only toggles whose compatibility window is complete.

## 7. Plugin/staging/doc cleanup

Check:

- `plugins/ultma/cog.py` loader contract;
- `externalization-staging/` if still present;
- `README.md`;
- `docs/architecture.md`;
- `docs/project-recommendations.md`.

Document or remove stale staging surfaces. Do not rewrite documentation wholesale.

## Tests

- parser compatibility tests;
- async-boundary tests;
- healthcheck missing/fresh/stale tests;
- config tests;
- import/dependency search evidence;
- full suite.

## Non-goals

- no new persistence system;
- no trading strategy changes;
- no broad UI/Discord redesign;
- no dependency upgrades unrelated to removal.

## Acceptance criteria

- [ ] parser monolith is decomposed by real domain boundaries.
- [ ] active Discord async paths avoid known blocking calls.
- [ ] healthcheck validates freshness.
- [ ] blanket volume chmod is removed if still present.
- [ ] only proven-unused dependencies are removed.
- [ ] completed compatibility toggles are cleaned up.
- [ ] architecture docs match final repository state.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report parser module map, async boundaries changed, healthcheck threshold, dependencies removed/retained with evidence, config compatibility removed, final architecture docs, and full test results.