# TP-20261013-002: Codex Error Watcher: Fail-Closed Diagnostics + Bounded State

**Packet ID:** TP-20261013-002  
**Status:** Complete  
**Created:** 2026-10-13  
**Last updated:** 2026-10-15  
**Repository:** braydio/RSAssistant  
**Target branch:** main  
**Canonical path:** `docs/task-packets/completed/TP-20261013-002-codex-error-watcher-sandbox-output-hardening.md`  
**Workstream size:** One implementation packet  
**Depends on:** None; coordinate log redaction with TP-20261010-005  
**Priority:** High  
**Authoring chat:** not-recorded  
**Expected packet count / order:** Two independent audit findings, TP-20261013-001 and TP-20261013-002; run 001 first due to trading-state correctness, then 002 or any existing priority work.  


## Objective

Preserve the optional **read-only** error-triage experience while preventing sensitive diagnostic material from being posted to Discord, blocking ambiguous invocation configuration, bounding in-memory message deduplication, and handling concurrent/error/timeouts cleanly. This is not autonomous code modification or trade execution.

## Confirmed current state (main, static audit 2026-10-13)

Exact seams: `rsassistant/bot/cogs/primary_channel_error_watcher.py`, `unittests/primary_channel_error_watcher_cog_test.py`, `utils/config_utils.py`, `config/.env.example`, `rsassistant/bot/core.py`.

- `PrimaryChannelErrorWatcherCog.on_message` checks enabled flag and trusted sender IDs. Channel check is conditional on a truthy `DISCORD_PRIMARY_CHANNEL`:
  ```python
  if (DISCORD_PRIMARY_CHANNEL and message.channel.id != DISCORD_PRIMARY_CHANNEL): return
  ```
  Since `DISCORD_PRIMARY_CHANNEL` defaults to 0 when invalid/missing, channel constraint silently vanishes when enabled.
- `_processed_message_ids: set[int] = set()` retains every processed ID for process lifetime; no TTL/size eviction and no concurrency guard besides `_last_run_at` timestamp.
- `_resolve_codex_cwd()` falls back to `Path.cwd()` when `AUTO_RSA_DIR` is missing/invalid, potentially examining the wrong repository.
- `_invoke_codex_exec` takes `CODEX_EXEC_COMMAND` through `shlex.split`, strips known dangerous Codex flags, appends `--sandbox read-only --ask-for-approval never`, runs `subprocess.run(... capture_output=True)` via `asyncio.to_thread`. The command **executable/prefix is not constrained** to Codex; appended flags alone cannot prove an overridden arbitrary executable is read-only.
- `_build_codex_prompt` correctly identifies error content as untrusted, and the code forces read-only when the binary honors flags; retain these protections.
- The cog **returns raw stdout/stderr** from external Codex and posts `result[:MAX_OUTPUT_CHARS]` inside Discord triple backticks. Truncation is **not redaction**. Discord content/prompt text or local diagnostics could include env secrets, raw tokens, or account identifiers. There is no test that outputs are safe.
- `unittests/primary_channel_error_watcher_cog_test.py` tests basic allowlist and force-read-only flags, but lacks unsafe command/invalid channel, output secret, cooldown race, timeout and bounded-memory regressions.
- Existing TP-20261010-005 addresses logging framework and LLM prompt logs, not this watcher state/Discord output path. Coordinate redactor helper if one lands; don't duplicate global logging framework changes.

## Required behavior / locked design

1. **Fail closed:** when `AUTO_RSA_ERROR_WATCHER_ENABLED=true`, require `DISCORD_PRIMARY_CHANNEL > 0`, nonempty trusted sender allowlist, explicit readable `AUTO_RSA_DIR` that is a directory, valid Codex executable, and validated safe invocation. If any prerequisite fails, log a sanitized configuration warning, disable watcher actions and provide an operator-facing setup warning on explicit status request only. Never fall back to a broader channel or unrelated cwd.
2. **Command allowlist:** accept only the approved Codex invocation shape (default `codex exec`, optionally absolute configured path ending in trusted `codex`, plus documented harmless flags). Reject arbitrary command names, extra shell wrappers, `--cd` pointing elsewhere, `--output-schema` to unsafe paths, `--json` if not handled, bypass flags and flag/value tricks. Do not claim read-only merely because unsafe options are stripped. Build explicit argv with non-overridable `--sandbox read-only --ask-for-approval never`; no `shell=True`.
3. **Never forward raw tool output:** turn Codex result into a **bounded, redacted operator summary** with status, high-level error type, sanitized file path/line if verified, and next action. Do not echo arbitrary stdout/stderr, Discord prompt content or potentially sensitive code fragments into a channel. If an allowlisted redaction pattern cannot make it safe, replace with `[details withheld; inspect local logs]`. No secret-bearing local logs either. Send-only to configured primary channel, plain text with `discord.AllowedMentions.none()` or equivalent; escape markup that could break formatting and avoid @everyone. Do not include account identifiers.
4. **Bounded dedupe and single-flight:** use capped `OrderedDict[message_id, observed_monotonic]` with e.g. max 1024 entries and 15-minute TTL; evict on access/insert. Guard the in-flight Codex process with an `asyncio.Lock` (or actual inflight task pointer) so a second message cannot start another process during the first. Cooldown measured with monotonic time, and categorize "skipped busy"/"skipped cooldown" without unbounded logging.
5. **Timeouts/exceptions:** report safe failure notices without raw subprocess stderr. `subprocess.run(timeout=...)` in a worker thread times out the process, but **not a detached parent/child process group in all cases**; document limitations and use bounded process-group termination only where portable/safe. Never run a new job automatically while an old child may still be alive. Do not perform automatic filesystem writes or code patches.
6. **Visibility:** add a small operator-only `..watcherstatus` command to report enabled/disabled, safe prerequisites, whether busy, sanitized last result/cooldown, and configuration keys needing attention (never their values). Leave watcher off by default. User-facing README must describe "read-only triage", not "auto-fix".

## Recommended code shape

New focused module `rsassistant/services/error_triage.py` for pure preflight/input/output sanitizer helpers **only if needed**; keep Discord integration in `rsassistant/bot/cogs/primary_channel_error_watcher.py`.

```python
def validate_codex_invocation(raw_command: str, cwd: Path) -> tuple[str, ...]:
    # verify codex executable and allowlisted argv; reject unsafe overrides
    return (codex_executable, "exec", "--sandbox", "read-only",
            "--ask-for-approval", "never")

def summarize_triage_result(*, exit_code: int, stdout: str, stderr: str,
                            runtime_context: dict) -> str:
    # bounded/redacted status + diagnostic category + local inspection advice
    # raw stdout/stderr never returned to Discord
    ...

async def on_message(...):
    if not watcher_preflight_ok or not trusted_message(...): return
    if inflight or cooldown_active or seen_recently(message.id): return
    mark_seen_bounded(message.id)
    async with single_flight:
        result = await run_readonly_codex(...)
    await send_safe_status(...)
```

Do not use subprocess output as instructions and do not pass arbitrary untrusted user message text as shell arguments outside the Codex prompt argument (which remains diagnostic data).

## Tests

Extend `unittests/primary_channel_error_watcher_cog_test.py`; add `unittests/error_triage_test.py` for pure validation/sanitization, mocked subprocess only.

- Enabled + primary channel ID 0/missing sender list/invalid `AUTO_RSA_DIR` -> **zero** Codex invocations.
- `CODEX_EXEC_COMMAND='python -c ...'`, shell wrapper, `codex exec --yolo`, extra directory override -> rejected. The valid default has exactly one read-only/never pair.
- Error content with token/email/account-like markers and Codex output with fake bearer/API keys, private paths and `@everyone` cannot reach Discord message or logs.
- 5000 unique message IDs -> bounded <=1024; TTL expiry works; duplicate IDs inside TTL skipped.
- Two concurrent qualifying messages -> at most one subprocess; subsequent retry after completion/cooldown behaves intentionally.
- Clean result, nonzero exit, thrown exception, subprocess timeout -> safe bounded status; no Discord embed/prompt echo; no unhandled background jobs.
- Disabled watcher remains inert; existing allowlist and sandbox tests remain green.
- Optional `..watcherstatus` accessible to operators only, credentials never displayed, no command triggers trading or file edits.

Commands:
```bash
python -m unittest unittests.primary_channel_error_watcher_cog_test unittests.error_triage_test
python -m unittest discover -s unittests -p '*_test.py'
python -m compileall -q rsassistant utils unittests
```

## Implementation order / coordination

1. Validate named files on latest main; check TP-20261010-005 implementation status, mark this packet/tracker In Progress.
2. Fail-closed config/command validator with tests. Update `config/.env.example` keys/descriptions if changed; avoid forced breaking behavior when watcher disabled.
3. Bounded single-flight event handling, TTL/cooldown tests.
4. Safe output summaries/status command, tests with realistic secret-bearing fixtures (synthetic only).
5. Update README and `docs/architecture.md` to explain read-only diagnosis, channel restrictions and local inspection; run validations.
6. On verified completion write `docs/task-packets/summaries/TP-20261013-002-SUMMARY.md`, move packet to completed and update INDEX/TRACKER atomically.

**Do not rediscover:** resource optimization TP-20261010-005 owns global log filtering; TP-20261010-003 owns network/Discord event loop; this is the **Codex watcher execution/output trust boundary**. Avoid redesigning the trading runtime or asking Codex to autonomously fix repo errors.

## Non-goals

No agent write access, autonomous code repair, auto-merge/deploy, trading operations, new remote telemetry, logging-framework refactor, persistent Discord message archive, or change to normal bot command processing.

## Acceptance criteria

- [ ] Enabled watcher has fail-closed channel, sender, repository and invocation preconditions.
- [ ] No arbitrary command override, dangerous flags or unexpected working-directory fallback.
- [ ] No raw Codex result, tokens, account IDs or Discord prompt injection rendered back to Discord.
- [ ] Seen-message dedupe bounded with TTL, single-flight/cooldown reliable, errors safely reported.
- [ ] Read-only sandbox, allowlist and disabled-by-default preserved.
- [ ] Operator status usable without exposing config values; regression tests pass.
- [ ] Durable completion summary with validation and any limitations.

## Completion report

Report status and commit URL, validated subprocess argv and output-redaction fixture results, test commands/results, persistent summary, remaining limitations and next higher-priority packet. Authoring chat: not-recorded.

