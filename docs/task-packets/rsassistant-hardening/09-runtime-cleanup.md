# Packet 09: Runtime Archaeology and Final Hardening

Commit: `chore: remove retired runtime baggage`

## Candidate files

- `utils/excel_utils.py`
- `unittests/excel_utils_test.py`
- `requirements.txt`
- `utils/config_utils.py`
- `config/.env.example`
- `docker-compose.yml`
- `Dockerfile`
- `entrypoint.sh`
- `.github/workflows/submit-pr.yaml`
- `scripts/healthcheck.py` (new if needed)
- `docs/architecture.md`
- `README.md`
- `AGENTS.md`

## Excel retirement

Run:

```
rg 'excel_utils|EXCEL_LOGGING_ENABLED|openpyxl'
```

If there is still no live production call site:
- delete `utils/excel_utils.py`
- delete its dedicated tests
- remove `openpyxl`
- remove the Excel Docker volume
- stop creating `$VOLUMES_DIR/excel`
- remove obsolete Excel runtime config/docs

If a production call site has appeared, do not delete it; report that single item as deferred.

## Dead Auto-PR workflow

Delete `.github/workflows/submit-pr.yaml` if it remains the broken workflow that creates `auto pr-submit` but pushes `auto-change`. CI from Packet 00 is the supported workflow.

## Healthcheck

Replace Docker's current existence-only:

```yaml
test: ["CMD", "cat", "/app/volumes/logs/heartbeat.txt"]
```

with a freshness check. Prefer a small `scripts/healthcheck.py` that exits nonzero if the heartbeat is missing or older than a reasonable threshold derived from the heartbeat cadence.

## Permissions

Remove the blanket:

```sh
chmod -R 755 "$VOLUMES_DIR"
```

Use only the permissions actually needed. Do not invent host UID/GID assumptions. A complete non-root container conversion is allowed only if bind-mounted volume behavior can be validated; otherwise explicitly defer that sub-item.

## Dependency pruning

Before removing any dependency, confirm zero runtime/test imports with `rg`. Review at least:
- `keyboard`
- `selenium`
- `webdriver_manager`
- `numpy`
- `rich`

Remove only proven-unused dependencies.

Update stale architecture/README/AGENTS references touched by this workstream. Do not rewrite documentation wholesale.

## Acceptance

- `python -m compileall .`
- `pytest -q`
- Docker healthcheck checks freshness, not file existence
- no retired Excel runtime artifacts remain if confirmed unused
- no dependency is removed while still imported
