# TP-20261010-008: Lean Docker Image, Startup I/O, and Health Checks

**Packet ID:** TP-20261010-008  
**Status:** Ready  
**Created:** 2026-10-10  
**Last updated:** 2026-10-10  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261010-008-lean-container-startup.md`  
**Workstream size:** One implementation packet in the 11-packet resource optimization train  
**Depends on:** None  
**Priority:** Normal  
**Authoring chat:** not-recorded  

## Objective

Reduce lean docker image, startup i/o, and health checks overhead while preserving live Discord behavior and all trading safety controls. Source audit baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`. If code drift invalidates a named seam, refresh this packet and tracker before implementation.

## Do not rediscover: exact files

- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `entrypoint.sh`
- `utils/logging_setup.py`
- `docs/architecture.md`
- `README.md`

## Confirmed current behavior

`Dockerfile` uses one Python 3.10-slim stage, installs build libraries and then removes only `build-essential`; `COPY . /app` depends on sparse `.dockerignore`. `entrypoint.sh` unconditionally runs `chmod -R 755 \"$VOLUMES_DIR\"` over persistent DB, cache and log trees, and exports `DISPLAY=:99` even headlessly. Docker healthcheck only checks that `heartbeat.txt` exists.

## Required changes and implementation order

1. Expand `.dockerignore` to exclude `.git`, `.venv`, `__pycache__`, runtime `volumes/**` except intentional tiny docs/fixtures, local `.env`, private creds, archived logs and error HTML/screenshots. Docker build context must retain source modules and bundled required config examples.
2. Use a builder/install stage for wheels/deps and a slim runtime stage, copying only needed runtime packages and `git` if still necessary for self-update. Do not remove Selenium/browser dependencies blindly: inspect actual runtime imports and verify against plugin usage. Pin a supported Python version and confirm numpy/pandas wheel compatibility.
3. Replace unconditional recursive `chmod` with directory creation and narrow `chmod` only on just-created paths or a documented opt-in permission-repair command. Preserve mounts/data ownership and nonroot compatibility; no removal of persisted data.
4. Remove unconditional DISPLAY override; document GUI-specific opt-in configuration. Replace healthcheck file-exists test with nonempty **fresh** heartbeat validation (e.g., file mtime within 2-3 heartbeat intervals), and ensure it does not themselves write heartbeat content. Keep interval and retry tolerant of startup.
5. Compose CPU/memory resource ceilings stay unchanged until measured evidence; do not set arbitrary lower limits that destabilize trading.

## Focused tests and validation

`docker compose config`, clean `docker build`, startup with existing mounted volume permissions, repeated startup with large volume tree, stale vs current heartbeat probe, and `python -m pytest -q unittests/core_startup_message_test.py`. Document before/after image bytes and startup time only after actually measured.

Run full repository tests when practical: `python -m unittest discover -s unittests -p '*_test.py'`. No live broker, Discord, SEC, LLM, or yfinance calls in automated tests.

## Acceptance criteria

- [ ] No recursive chmod on normal boot; live container can read/write data; stale heartbeat fails; build context excludes sensitive runtime debris; image and startup changes validated.
- [ ] Existing public APIs and safety constraints preserved.
- [ ] Tests and measured before/after observations (if available) included in durable completion summary.
- [ ] Update `docs/task-packets/INDEX.md` and `TRACKER.md` on lifecycle transition, and create `docs/task-packets/summaries/TP-20261010-008-SUMMARY.md` per `AGENTS.md`.

## Non-goals

No runtime CPU quota cuts, volume deletion, or change to auto-rsa sibling service ownership.

## Completion report

Report outcome, file list, tests, performance observations versus baseline (mark `not-measured` if unavailable), residual risks, any blocker or drift, and recommended next packet. For dependency-gated Draft work, **do not implement until prerequisite completion is reviewed and this packet is explicitly promoted to Ready**. Authoring chat: not-recorded (do not invent a URL).
