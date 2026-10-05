# TP-20261003-002: Establish a Full CI Baseline

**Packet ID:** TP-20261003-002  
**Status:** Complete
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261003-002-ci-baseline.md`
**Workstream size:** One implementation packet  
**Depends on:** None

## Objective

Make every push to `main` and every pull request run repository compilation and the complete unittest suite, and remove the stale workflow that attempts to create an unrelated auto-generated PR.

## Confirmed current state

- `.github/workflows/ci.yml` runs `compileall` only on selected source directories and invokes pytest against a fixed subset of tests.
- `requirements-dev.txt` includes `requirements.txt` and pytest; the project instructions define unittest discovery as the suite command.
- `.github/workflows/submit-pr.yaml` is a workflow-dispatch job that modifies the checkout, uses inconsistent branch names, and attempts to open an unrelated PR.
- `unittests/command_error_handler_test.py` still calls `RSAssistant.on_command_error`, but the entrypoint now delegates to the modular bot and the handler is `RSAssistantBot.on_command_error` in `rsassistant/bot/core.py`.

## Required changes

### `.github/workflows/ci.yml`

Keep CI on pushes to `main` and pull requests. Keep the existing Python setup and dependency installation, then run:

```bash
python -m compileall .
python -m unittest discover -s unittests -p '*_test.py'
```

Do not convert the suite to pytest in this packet.

### `.github/workflows/submit-pr.yaml`

Delete the stale workflow. It is not a CI check and its branch/PR behavior is broken.

### `unittests/command_error_handler_test.py`

Update the test to exercise the current `RSAssistantBot.on_command_error` method and obtain the configured fallback prefix from `utils.config_utils`. Do not add a legacy handler export to `RSAssistant.py`; its documented role is only to delegate to the modular runtime.

## Tests and validation

Run locally:

```bash
python -m compileall .
python -m unittest discover -s unittests -p '*_test.py'
```

Inspect the resulting workflow to confirm it triggers on normal pushes to `main` and pull requests and contains both validation commands.

## Non-goals

- Do not convert unittest tests to pytest.
- Do not change application code or dependency sets.
- Do not add generated commits, branches, or pull requests to CI.

## Implementation order

1. Update `.github/workflows/ci.yml` to run full compile and unittest discovery.
2. Delete `.github/workflows/submit-pr.yaml`.
3. Update the stale command error tests to call the modular bot handler.
4. Run the validation commands and inspect the final diff.
5. Move this packet to `completed/` and update `INDEX.md` and `TRACKER.md`.

## Acceptance criteria

- [ ] Pushes to `main` and pull requests trigger CI.
- [ ] CI runs `python -m compileall .`.
- [ ] CI runs unittest discovery across `unittests/` using `*_test.py`.
- [ ] The stale `submit-pr.yaml` workflow is removed.
- [ ] Command error tests target the current modular bot handler.
- [ ] Both local validation commands pass.

## Completion report

Report the workflow changes and exact validation results. Record any environmental limitation or failure without weakening the acceptance criteria.
