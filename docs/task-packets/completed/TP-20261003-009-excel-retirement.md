# TP-20261003-009: Excel Runtime Retirement

**Packet ID:** TP-20261003-009
**Status:** Complete
**Created:** 2026-10-03
**Last updated:** 2026-10-04
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/completed/TP-20261003-009-excel-retirement.md`
**Workstream size:** One implementation packet
**Depends on:** TP-20261003-008
**Priority:** Normal
**Controller:** TP-20261003-001

## Required dependency-refresh checkpoint

This packet was authored before TP-20261004-008 landed and was refreshed against its completed implementation on 2026-10-04. The order-history changes do not change the Excel retirement seam. Dependency review conversation: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Review finding: the only production references outside `utils/excel_utils.py` and `utils/config_utils.py` are the Docker volume mount, entrypoint directory creation, and a deprecation warning in `utils/watch_utils.py`. Update the config contract's `persistence` object to remove its `excel` key and update its exact test assertion. Update the watchlist test that currently expects the Excel warning. These are part of this packet's retirement scope.


## Objective

Remove the now-dead Excel runtime surface after SQL authority has been established for the domains Excel historically supported.

## Preconditions

Before deletion, run:

```bash
rg -n "excel_utils|EXCEL_LOGGING_ENABLED|EXCEL_FILE_MAIN|openpyxl|volumes/excel|ReverseSplitLog.xlsx" .
```

Classify every match.

If a production call site still requires Excel, stop and use the review link rather than weakening this packet.

## Expected removals

### Code/tests

- delete `utils/excel_utils.py`;
- delete `unittests/excel_utils_test.py`;
- remove Excel imports/references from any remaining production module;
- in `utils/watch_utils.py::watch_ticker()`, remove the obsolete Excel deprecation warning and adjust its docstring;
- update `unittests/watch_utils_test.py` so it verifies watchlist updates without expecting an Excel warning.

### Dependencies

From `requirements.txt` remove:

```text
openpyxl==...
```

only after zero imports.

### Configuration

Remove/deprecate completely:

- `EXCEL_LOGGING_ENABLED`;
- `EXCEL_FILE_MAIN`;
- Excel runtime path resolution;
- `EXCEL_LOGGING_ENABLED` from `config/.env.example`.

Update config tests accordingly.

### Container/runtime

`docker-compose.yml`:

remove:

```yaml
- ./volumes/excel:/app/volumes/excel
```

`entrypoint.sh`:

remove `$VOLUMES_DIR/excel` from `REQUIRED_DIRECTORIES`.

### Documentation

Update:

- `README.md`;
- `docs/architecture.md`;
- `docs/excel_to_sql_mapping.md`.

Keep `docs/excel_to_sql_mapping.md` as historical migration documentation, headed clearly that migration is complete and no runtime Excel dependency remains.

## Compatibility

Do not delete historical user Excel files from `volumes/excel`. Stop mounting/creating/reading them. User-owned data is not repo cleanup.

Do not add a replacement spreadsheet library.

## Tests

- config imports with Excel env absent;
- bot startup without Excel directory;
- Docker/config docs no longer require Excel;
- watchlist updates no longer emit the Excel deprecation warning;
- search assertion/test may ensure `openpyxl` and `utils.excel_utils` have no production imports.

## Dependency refresh findings

- TP-20261004-008 adds SQL order-history authority and does not import or depend on Excel code.
- Current production import search finds no `utils.excel_utils` consumers outside the module itself.
- `utils.config_utils` still exposes the Excel path, toggle, log message, and `persistence.excel` value; the path/toggle/config shape changes are included above.
- `utils.watch_utils.WatchListManager.watch_ticker()` logs an Excel deprecation warning. This stale behavior and its test are included above.
- `rg` hits in migration documentation, historical packets, and the modernization controller are documentation references; preserve or update them according to the documentation requirements below.

## Non-goals

- no CSV removal beyond already-demoted domains;
- no persistence repository decomposition;
- no business logic changes.

## Acceptance criteria

- [x] no production Excel module/import.
- [x] no openpyxl dependency.
- [x] no Excel config toggle/path.
- [x] no Docker Excel mount/startup directory.
- [x] historical mapping doc remains for audit context.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Implemented Excel retirement across runtime code, config, dependency, Docker, startup, docs, and tests. Deleted `utils/excel_utils.py` and its tests; removed the obsolete watchlist warning and `persistence.excel` config entry. Updated the canonical index/tracker and moved this packet to `completed/`.

Validation: focused pytest run passed 18 tests with one unrelated existing config migration test deselected; compileall passed; full unittest discovery passed all 80 tests. Full pytest reported 148 passed and 8 failures in legacy tests that expect removed `RSAssistant` exports, assert a stale parser snippet, depend on real legacy account data during an isolated SQL test, or call a Discord command callback without its required context. These failures are unrelated to Excel retirement and were left unchanged, as the packet directs.

Final search found no Excel runtime symbols/imports in production source, dependencies, Docker, or config. References remain in historical mapping/task documentation, a README migration note, and regression tests that assert removed configuration and directory behavior. User-owned workbook files were left untouched.
