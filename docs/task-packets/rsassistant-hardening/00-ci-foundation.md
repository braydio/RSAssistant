# Packet 00: Executable Test Baseline

Commit: `ci: establish executable test baseline`

## Files

- `requirements-dev.txt` (new)
- `.github/workflows/ci.yml` (new)
- `utils/watch_list_manager.py` (delete only if still unreferenced)
- `AGENTS.md` (update test command/framework after migration)
- test files only if required to make the documented runner match the suite

## Changes

1. Confirm `utils/watch_list_manager.py` has no production import with:
   `rg 'watch_list_manager'`.
   The active manager is `WatchListManager` in `utils/watch_utils.py`. If no live import exists, delete the malformed dead module.
2. Create `requirements-dev.txt`:
   ```
   -r requirements.txt
   pytest>=8,<9
   ```
3. Add `.github/workflows/ci.yml` for push/PR to `main`, Python 3.10, installing `requirements-dev.txt`, then:
   ```
   python -m compileall .
   pytest -q
   ```
4. Update `AGENTS.md` Testing Guidelines and dev command to use pytest. This packet supersedes the current legacy unittest-runner instruction because existing tests already use pytest fixtures/functions.
5. Do not repair `.github/workflows/submit-pr.yaml` here.

## Acceptance

- `python -m compileall .` succeeds.
- `pytest -q` actually discovers the existing pytest-style tests.
- CI uses the same two commands.
- No production behavior changes.
