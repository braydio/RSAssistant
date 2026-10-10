# RSAssistant Resource Optimization Audit — 2026-10-10

Repository: `braydio/RSAssistant`  
Static review baseline: `main@b35ea9480e184bff059517994f3d2bfd2c751596`

## Scope and confidence

This is a code-path review, not a live profile. Real CPU/RSS, bandwidth, disk writes and event-loop drift are **not measured**. TP-20261010-001 establishes measurements. Estimated impact labels below are priority hypotheses, not performance claims.

| Opportunity | Evidence | Likely resource/behavior effect | Packet |
| --- | --- | --- | --- |
| Threaded scheduler inside async runtime | `rsassistant/bot/tasks.py::_start_reminder_scheduler` creates `BackgroundScheduler` and thread->event-loop lambdas | Extra background thread and lifecycle complexity | 002 |
| Blocking policy/SEC/LLM network | `rsassistant/bot/handlers/on_message.py::handle_secondary_channel`; `utils/policy_resolver.py` uses requests | Discord message latency and heartbeat risk under slow responses | 003 |
| Price fetching in async commands | `utils/watch_utils.py::list_watched_tickers,send_watchlist_prices` call sync yfinance helper | Discord event loop may be blocked | 003 |
| Polling log and failed-import suppression | `utils/holdings_importer.py::import_holdings_if_updated` logs unchanged checks at INFO and records mtime even after failed import | Repeated log I/O and possible stale holdings after bad file | 004 |
| Unbounded dedupe state and prompt logging | `utils/logging_setup.py::TimeLengthListDuplicateFilter`; `utils/openai_utils.py` | Slow memory growth, disk churn and sensitive notice logging | 005 |
| Unbounded ticker and failure price maps | `utils/price_fetcher.py::_CACHE,_FAILED_ATTEMPTS`; whole-file JSON rewrite | RAM/disk growth with large symbol histories | 006 |
| Optional trading plugin sync fetches | `plugins/ultma/ult_ma_bot.py::_monitor_loop,_check_position`; `market_data.py::fetch_candles` | Potential event-loop stalls during yfinance retries | 007 |
| Recursive startup chmod, large image context | `entrypoint.sh`, `Dockerfile`, `.dockerignore` | Repeated metadata writes and image build overhead | 008 |
| Tracked debug logs and 4MB HTML captures | `volumes/archive/docker-logs-legacy/`, `volumes/db/fidelity_errors/` | Clone/build context size and accidental data exposure risk | 009 |
| O(tickers × rows) CSV summary | `rsassistant/bot/cogs/holdings.py::show_reminder` calls `utils/utility_utils.py::track_ticker_summary` per ticker | Repeated full-snapshot reads | 010 (blocked by modernization) |
| Long-lived per-order tasks | `utils/order_exec.py::schedule_and_execute`, `rsassistant/bot/tasks.py::reschedule_queued_orders` | Number of retained tasks scales with queued orders | 011 (blocked by TP-004) |

## Preserve trading correctness

- No adaptive refresh throttling in this train that could miss market events.
- No shortening safety lookbacks, stale-quote reuse, unsanctioned reductions of API checks, or changes in order effective time.
- Never delete durable order/holdings/audit records to save space.
- Existing persistence modernization TP-20261003-002..012 and performance history TP-20261004-001/002 remain authoritative for SQL ownership and domain decomposition.
- Test external network/broker calls with mocks.
- Before/after numbers belong in completion summaries and must be genuinely measured; no benchmark fabricated from static review.

## Suggested execution

Run independent low-risk work in priority order: observability (001), logging (005), importer (004), asyncio scheduler (002), nonblocking HTTP (003), bounded price cache (006), optional ULT-MA (007), Docker (008), data hygiene (009). Evaluate 010 and 011 only after their predecessor work lands and packet refresh confirms APIs.

If a Ready optimization packet intersects newly landed modernization code, keep the intent but update the precise seam and tracker before editing; do not fork the persistence architecture.
