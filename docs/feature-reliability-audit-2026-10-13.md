# RSAssistant Focused Feature / Reliability Audit (2026-10-13)

Baseline: `braydio/RSAssistant` at main as inspected 2026-10-13. **Static review**, not a runtime profile, benchmark or full security penetration test; performance impact and exploitability are not measured. Canonical execution packets are in `docs/task-packets/active/`; this audit is a reference, **not** an executable packet.

## Existing coverage: do not duplicate

- 2026-10-10 eleven-packet resource optimization train: baseline instrumentation (001), asyncio scheduler (002), nonblocking network (003), holdings importer (004), logging (005), price cache (006), ULTMA (007), Docker (008), artifacts (009), holdings single-pass SQL (010 Draft), order task consolidation (011 Draft).
- Modernization: TP-20261003-001 controller; SQLite order queue, split-monitor state, holdings authority, order history, and performance history already exist. TP-20261003-012 parser/runtime cleanup Draft pending dependency refresh.
- TP-20261004-001 and 002 (performance capture and visibility) are complete. Avoid reopening them from old docs.

## Confirmed highest-value gaps and new packets

| Priority | Evidence on current main | Why it matters | Canonical packet |
| --- | --- | --- | --- |
| High | `utils/split_watch_utils.py::cleanup_expired_tickers` deletes split_monitor rows solely by past effective date; `SplitMonitorCog.split_status` calls cleanup as a side effect; `on_message._process_round_up_flow` checks `get_status` then independently calls `add_split_watch` and schedules autobuys | Unsold accounts can vanish from live tracking; concurrent/replayed alerts can create duplicate automated order intents | [TP-20261013-001](task-packets/active/TP-20261013-001-split-event-lifecycle-and-autobuy-idempotency.md) |
| High | `PrimaryChannelErrorWatcherCog` stores an unbounded `_processed_message_ids` set; optional channel constraint fails open for 0; configured command prefix and cwd fallback are not strictly validated; raw Codex stdout/stderr is posted to Discord | Security, operator control and memory risk in optional diagnostics path | [TP-20261013-002](task-packets/active/TP-20261013-002-codex-error-watcher-sandbox-output-hardening.md) |

## Candidates for later targeted audits (not in new executable packets)

- **Operator exception digest**: a read-only summary of outstanding split events, unresolved order intents, stale holdings refresh, and latest confirmed broker import; should reuse existing persisted SQL states, not establish a second operational store. Defer until lifecycle and importer correctness packets land.
- **Policy provenance / manual review**: compare parsed NASDAQ vs SEC vs LLM fractional-share evidence, confidence and effective date before automated action; overlap with `utils/policy_resolver.py` and TP-20261003-012 parser refactor should be reviewed rather than drafted prematurely.
- **Broker-level autobuy coverage**: `rsassistant/services/order_orchestration.py::build_watchlist_autobuy_commands` deduplicates per (ticker,broker) even when missing holdings were detected per account. Verify actual `auto-rsa` broker-wide command semantics before proposing per-account orders; changing this without proof could create extra trades.
- **Orders operational reconciliation**: pending/unknown delivery and restart state are covered in Draft TP-20261010-011; refresh that packet against current SQL tables before adding further work.

## Recommended execution

Start TP-20261013-001 for correctness/risk containment. TP-20261013-002 is independent and can follow. Work the existing runtime-optimization train separately in its documented priority order. Do not infer realized CPU, latency or trade-safety gains before focused tests and runtime measurement. No trading app code was changed in this audit commit.
