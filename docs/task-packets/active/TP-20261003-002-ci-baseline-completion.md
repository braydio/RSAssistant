# TP-20261003-002: CI Baseline Completion

**Packet ID:** TP-20261003-002  
**Status:** Ready  
**Created:** 2026-10-03  
**Last updated:** 2026-10-03  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/active/TP-20261003-002-ci-baseline-completion.md`  
**Workstream size:** One implementation packet  
**Depends on:** None  
**Priority:** High  
**Controller:** TP-20261003-001  

## Objective

Finish the partially-landed CI foundation so every normal push/PR gets a trustworthy full test gate before persistence work continues.

## Confirmed current state

Exact files:

- `.github/workflows/ci.yml`
  - exists;
  - uses Python 3.12;
  - installs `requirements-dev.txt`;
  - runs compileall;
  - runs only a hand-picked subset of pytest files.
- `requirements-dev.txt`
  - exists and includes `-r requirements.txt` plus `pytest>=8,<9`.
- `.github/workflows/submit-pr.yaml`
  - still exists;
  - creates branch text with `git checkout -b auto pr-submit` but pushes `auto-change`;
  - is unrelated to CI and should not remain as the supported automation path.

Do not rediscover the test framework. The repository now has pytest available and many tests are pytest-style functions.

## Required changes

### 1. `.github/workflows/ci.yml`

Replace the focused file list with the full test suite:

```yaml
- run: python -m compileall -q rsassistant utils plugins unittests
- run: python -m pytest -q
```

Keep:

- push to `main`;
- pull_request trigger;
- `actions/checkout@v4`;
- `actions/setup-python@v5`;
- Python 3.12;
- pip cache;
- install from `requirements-dev.txt`.

If full pytest exposes a known environment-only test, fix the test isolation rather than shrinking CI back to a curated list.

### 2. `.github/workflows/submit-pr.yaml`

Delete it.

Do not replace it with another auto-generated-PR workflow in this packet.

### 3. Local baseline

Run the exact CI commands locally.

If there are current-main failures unrelated to this packet, capture the failing test names in the packet completion report. Only fix them if they are required to establish a green baseline and the fix is bounded.

## Tests

No new product tests are required unless CI exposes a deterministic test-environment defect.

## Non-goals

- no pytest migration/refactor;
- no coverage threshold;
- no lint framework introduction;
- no persistence changes;
- no application behavior changes.

## Implementation order

1. run full pytest on current main;
2. identify whether baseline is green;
3. broaden `ci.yml`;
4. remove `submit-pr.yaml`;
5. run compileall + full pytest again.

## Acceptance criteria

- [ ] CI runs full `python -m pytest -q`.
- [ ] CI runs compileall.
- [ ] `submit-pr.yaml` is gone.
- [ ] `requirements-dev.txt` remains sufficient for CI.
- [ ] no persistence/product behavior changes are mixed in.

## Validation

Run focused tests named above, then:

```bash
python -m compileall -q rsassistant utils plugins unittests
python -m pytest -q
```

Do not repair unrelated pre-existing failures without documenting them.


## Completion report

Report the final CI commands, test count/result, files changed, and any baseline failures that had to be corrected.