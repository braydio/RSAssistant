# TP-20261003-009: Excel Runtime Retirement

**Packet ID:** TP-20261003-009
**Status:** Draft
**Created:** 2026-10-03
**Last updated:** 2026-10-03
**Repository:** braydio/RSAssistant
**Target branch:** main
**Canonical path:** `docs/task-packets/active/TP-20261003-009-excel-retirement.md`
**Workstream size:** One implementation packet
**Depends on:** TP-20261003-008
**Priority:** Normal
**Controller:** TP-20261003-001

## Required dependency-refresh checkpoint

This packet was authored **before TP-20261003-008 landed**. Do not implement it blindly after the dependency merges.

Before coding:

1. pull/re-open current `main`;
2. read TP-20261003-008's completion report and diff;
3. compare this packet's named files, schema assumptions, and public APIs against current main;
4. if any material assumption changed, **stop before implementation** and call out that this packet needs review/refresh;
5. include this review link in that handoff:

https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Suggested handoff wording:

> TP-20261003-008 has landed. The next packet was pre-authored and needs a dependency refresh against current main before implementation. Review/update it here: https://chatgpt.com/c/6abd8dc2-cab4-83e9-a614-b554cf5dd69e

Do not silently reinterpret stale instructions.


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
- remove Excel imports from any remaining module.

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
- search assertion/test may ensure `openpyxl` and `utils.excel_utils` have no production imports.

## Non-goals

- no CSV removal beyond already-demoted domains;
- no persistence repository decomposition;
- no business logic changes.

## Acceptance criteria

- [ ] no production Excel module/import.
- [ ] no openpyxl dependency.
- [ ] no Excel config toggle/path.
- [ ] no Docker Excel mount/startup directory.
- [ ] historical mapping doc remains for audit context.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Provide final `rg` results for Excel symbols and list intentionally retained historical documentation/data references.
