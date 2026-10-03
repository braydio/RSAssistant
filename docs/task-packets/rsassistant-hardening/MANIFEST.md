> [!WARNING]
> **Legacy pre-canonical workstream. Do not execute this manifest directly against current `main`.**
> The canonical packet system is `docs/task-packets/README.md`, `INDEX.md`, and `TRACKER.md`.
> This train is preserved as design history under archived wrapper `TP-20260612-001`. Reuse requirements only by copying/rebasing them into a new canonical packet.

# RSAssistant Hardening Workstream

Baseline at workstream creation: `main@03d1b815af3f491a88ae8c45a46eb8dce5a19d4e`.

Run packets strictly in numeric order. Each packet is one fresh Codex invocation and one commit.

- [ ] `00-ci-foundation.md`
- [ ] `01-order-integrity.md`
- [ ] `02-command-authorization.md`
- [ ] `03-runtime-trust-boundaries.md`
- [ ] `04-market-scheduling.md`
- [ ] `05-correctness-cleanup.md`
- [ ] `06-order-persistence-sqlite.md`
- [ ] `07-split-monitor-sqlite.md`
- [ ] `08-async-runtime.md`
- [ ] `09-runtime-cleanup.md`

## Agent protocol

For each packet:

1. Read `AGENTS.md`, this manifest, and only the next unchecked packet.
2. Read only files named by that packet plus direct dependencies/tests required to implement it.
3. Do not perform a repository-wide review.
4. Do not change files outside packet scope unless compilation/tests prove a direct dependency requires it.
5. Make the smallest implementation satisfying the packet acceptance criteria.
6. Run the packet's focused tests.
7. Run `python -m compileall .`.
8. Run `pytest -q` once Packet 00 has established pytest; during Packet 00 install/use its dev requirements first.
9. Fix failures caused by the packet. Verify unrelated failures existed before the packet rather than repairing unrelated code.
10. Inspect `git diff` and remove unrelated changes.
11. Mark only the current packet complete in this manifest.
12. Commit using the packet's specified commit message.
13. Stop. The runner launches the next packet in a fresh Codex process.

Do not skip a failed packet. Stop if implementation requires an unspecified product/design decision, unavailable external dependency, or a prerequisite outside scope.

## Scope boundary

This workstream intentionally does not perform a broad service-layer rewrite of `utils/sql_utils.py` or `rsassistant/bot/handlers/on_message.py`. Finish the bounded safety, persistence, async, and cleanup work first.
