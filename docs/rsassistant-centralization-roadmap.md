# RSAssistant Centralization Review & Roadmap (AutoRSA Assistant)

Date: 2025-12-26

## Executive Summary

The repository is already mid-refactor toward a **modular Discord bot**
(`rsassistant/bot/*`) with **thin cogs** that delegate most work to existing
`utils/*` modules. In parallel, optional functionality has been
**externalized into `externalization-staging/`** (ULT‑MA trading plugin, devops
watchers, autoRSA overrides).

To get to a “focused and centralized assistant to the auto-rsa bot,” the main
work remaining is not a rewrite—it’s:
1) **Deduplicate** overlapping implementations and remove dead/broken modules.
2) **Centralize state** (reverse split cases, split-watch progress, dedupe
   caches) under a single persistence root.
3) Replace “incidental automation” with one explicit, testable pipeline:
   **RSS intake → policy/ratio extraction → case state → order plan → execution
   → reconciliation**.

This report documents the current flows, the refactor state, and a concrete
step-by-step roadmap to finish the consolidation and unlock full automation.

---

## Current Repository State (What Runs Today)

### Entrypoints
- `RSAssistant.py`
  - Default: if `RSASSISTANT_ENTRYPOINT` is `modular`/`true`/`1`, it calls
    `rsassistant.bot.core.run_bot()` and exits.
  - Legacy: otherwise it runs a monolith that **re-defines commands and tasks**
    a second time.
- `rsassistant/bot/core.py`
  - Creates `RSAssistantBot`, loads core cogs, starts background tasks from
    `rsassistant/bot/tasks.py`, and routes messages into
    `utils/on_message_utils.py`.

### “Modular” Bot = Cogs + Existing Utils
The modular cogs are mostly wrappers over utilities:
- Watchlist commands → `utils/watch_utils.py`
- Order scheduling → `utils/order_exec.py` + `utils/order_queue_manager.py`
- Holdings refresh/audit → `utils/on_message_utils.py` + `utils/parsing_utils.py`
- Reverse split monitoring commands → `utils/split_watch_utils.py`

### Message ingest (primary + secondary channels)
`utils/on_message_utils.py` is the operational center:
- Primary channel:
  - Parses holdings embeds and persists holdings
  - Parses autoRSA order outputs (via `utils/parsing_utils.parse_order_message`)
  - Runs watchlist audit windows (`..all` flow), over-$ alerting + optional auto-sell
  - Hosts operational commands (`..updatebot`, `..revertupdate`)
- Secondary channel:
  - Parses RSS relay messages (MonitoRSS-style) into ticker + URL
  - Fetches/derives fractional-share policy and effective date
  - Posts summary/snippet to tertiary channel (fallback to primary)
  - If “round up” confirmed, schedules a buy and starts split-watch tracking

### Reverse split automation flow (current)
When a “reverse stock split” alert arrives in the secondary channel:
1. Parse ticker + URL via `utils/parsing_utils.alert_channel_message()`
2. Fetch/analyze sources via `utils/policy_resolver.SplitPolicyResolver.full_analysis(url)`
3. Post summary/snippet via `utils/on_message_utils.post_policy_summary()`
4. If `round_up_confirmed`:
   - Schedule autobuy (`quantity=1`, `broker="all"`) via
     `utils/on_message_utils.attempt_autobuy()` → `utils/order_exec.schedule_and_execute()`
   - Add a split-watch entry via `utils/split_watch_utils.add_split_watch()`
5. As holdings/orders arrive later, `utils/parsing_utils` updates split-watch
   progress:
   - Holdings parse can mark “bought” when the ticker appears
   - Completed sell orders can mark “sold” when the ticker is tracked

This is a strong “pipeline proof,” but it is not yet a complete case manager:
- No split ratio extraction (required for real planning)
- No idempotent case store (dedupe across repeated RSS notices)
- No broker/account strategy rules
- No post-split reconciliation-driven sell planning
- Split-watch state stored in a nonstandard location (`split_watchlist.json` at repo root)

---

## Refactoring Already in Progress (Evidence in Repo)

### 1) Modularization exists, but legacy still duplicates it
- Implemented: `rsassistant/bot/core.py`, `rsassistant/bot/tasks.py`, `rsassistant/bot/cogs/*.py`
- Still present: `RSAssistant.py` legacy monolith that duplicates many of the same commands.

### 2) Externalization exists, but plugin wiring is incomplete
`externalization-staging/` includes:
- `plugins/ultma/*` (ULT‑MA strategy + tests)
- `devops/*` (PR watcher + DeepSource monitor + tests)
- `custom-overrides/*` (autoRSA patches)

But:
- `rsassistant/bot/core.py` expects plugins at `plugins.{name}.cog`
- The repo’s `plugins/` directory is empty (plugin contract isn’t finalized/wired).

### 3) Configuration consolidation is underway
- `utils/config_utils.py` loads env from `config/.env` (or `ENV_FILE`) and exports constants.
- `config/settings.yml` remains present but appears legacy/compat only; `load_config()` now synthesizes a dict from env values.

### 4) Dedup/reliability improvements have started, but overlaps remain
Examples:
- Text normalization for “cash in lieu” OCR variants: `utils/text_normalization.py`
- A more structured policy classifier exists: `utils/helper_api.py`
  - But `utils/policy_resolver.py` also implements its own classification logic.

---

## Fragmentation & Duplication (High-Impact Targets)

### A) Two bot implementations coexist
- Modular bot: `rsassistant/bot/*`
- Legacy bot: `RSAssistant.py` defines the same commands and flow again.

Impact:
- Feature changes can land in one path but not the other.
- Operational debugging is ambiguous (“which runtime executed?”).

Recommendation:
- Treat legacy mode as a temporary compatibility layer with an explicit removal plan.

### B) Reminder scheduling is duplicated and likely double-fires
In modular mode:
- `rsassistant/bot/tasks.py` starts `periodic_check(bot)` from `utils/watch_utils.py` (which schedules reminders inside a `while True` loop)
- `rsassistant/bot/tasks.py` also starts an APScheduler reminder scheduler that calls `send_reminder_message(bot)`.

Impact:
- Reminders can run twice and at mismatched times.

Recommendation:
- Choose **one** scheduling mechanism (APScheduler *or* async loop) and retire the other.

### C) Secondary-channel RSS parsing exists in multiple places
Dead/unused duplicate:
- `utils/secondary_alert_parser.py` re-implements `alert_channel_message` and an older handler.

Active:
- `utils/parsing_utils.alert_channel_message()` (used by `utils/on_message_utils.py`)

Recommendation:
- Remove/retire the unused parser module and keep a single intake path.

### D) Fractional-share policy logic is duplicated
Overlapping implementations exist in:
- `utils/policy_resolver.SplitPolicyResolver.analyze_fractional_share_policy()`
- `utils/helper_api.analyze_fractional_share_policy()` (structured output)
- `utils/reverse_split_parser.get_reverse_split_handler_from_url()` (appears unused)

Recommendation:
- Pick **one canonical classifier** (prefer `utils/helper_api.py`) and have other layers call into it.

### E) Reverse split state is fragmented and stored inconsistently
- Split watch: `utils/split_watch_utils.py` stores `split_watchlist.json` at repo root
- Watchlist/sell list: `config/watch_list.json`, `config/sell_list.json` via `utils/watch_utils.py`
- Daily dedupe cache: `config/overdollar_actions.json` via `utils/monitor_utils.py`

Recommendation:
- Move all runtime state under **one root** (`VOLUMES_DIR/db`), and keep operator-edited config under `config/`.

### F) Broken/obsolete code exists in `utils/`
- `utils/watch_list_manager.py` is syntactically invalid and appears unused.
- `utils/reverse_split_parser.py` appears unused.
- `utils/secondary_alert_parser.py` appears unused.

Recommendation:
- Quarantine or delete unused/broken modules to reduce cognitive overhead and accidental imports.

---

## Target “Focused Core” Definition (AutoRSA Assistant)

If RSAssistant’s purpose is “a centralized assistant to autoRSA,” the focused core should be:
1. Discord IO + routing
2. Reverse split case intake (RSS + manual)
3. Policy + ratio extraction (NASDAQ/SEC/press)
4. Case lifecycle state (detected → planned → bought → post-split → sold → archived)
5. Order planning + execution (via autoRSA, with safeguards)
6. Reconciliation (parse autoRSA orders/holdings; update case status)
7. Operator reporting (status, queue, exceptions, audit)

Everything else should be optional/external:
- Devops watchers
- Trading strategies
- autoRSA overrides/fork artifacts

---

## Roadmap: Deduplication + Refactoring Steps (Recommended Order)

### Phase 0 — Decide and document the one true runtime
1. Make “modular bot” the only supported path; treat legacy as “break glass only.”
2. Add a clear deprecation timeline for the legacy monolith.
3. Ensure README + docs communicate the runtime choice unambiguously.

### Phase 1 — Eliminate duplicate implementations and dead modules
1. Retire/remove unused modules:
   - `utils/secondary_alert_parser.py`
   - `utils/reverse_split_parser.py`
   - `utils/watch_list_manager.py` (or move to a quarantine folder until fixed)
2. Ensure there is exactly one implementation for:
   - Secondary alert parsing (`alert_channel_message`)
   - Fractional policy classification
   - Account nickname resolution (currently duplicated across `utils/config_utils.py`, `utils/parsing_utils.py`, and `utils/on_message_utils.py`)

### Phase 2 — Centralize state and remove hidden globals
1. Move split watch persistence out of repo root:
   - Replace `split_watchlist.json` with a path under `VOLUMES_DIR/db/` (runtime state)
2. Convert module-level globals to explicit stores:
   - `SplitWatchStore`
   - `WatchListStore`
   - `ActionDedupStore`
3. Remove `set_channels()` globals where possible; prefer reading IDs from `utils/config_utils.py` and resolving channels via `utils/channel_resolver.py`.

### Phase 3 — Introduce a Reverse Split “Case Manager”
Create one concept representing a single reverse split opportunity:
- `ReverseSplitCase` (ticker, sources, effective date, ratio, policy, status, per-account progress, planned orders)
- `CaseStore` (persist cases; supports idempotent updates and intake dedupe)

Then route automation through it:
- RSS intake creates/updates cases (idempotent)
- Order/holdings ingestion updates case progress
- Planner schedules buy/sell actions based on case status and policy

### Phase 4 — Make AutoRSA integration a first-class gateway
Currently autoRSA integration is spread across string formatting, channel selection, queueing, and parsing.

Recommendation:
- Create one `AutoRSAGateway` interface with two transports if desired:
  - Discord transport (`!rsa ...` commands)
  - HTTP transport (`AUTO_RSA_BASE_URL`) when available

### Phase 5 — Restore the plugin story (optional features only)
1. Finalize the plugin contract expected by `rsassistant/bot/core.py` (`plugins.{name}.cog`).
2. Either:
   - Extract `externalization-staging/plugins/ultma` into an installable repo, or
   - Temporarily host it under `plugins/ultma/` in this repo until extraction is complete.

---

## Roadmap: Full Automation for Fractional Round-Up Reverse Splits

To “fully automate reverse split with fractional share roundup handling + automatic order execution with RSS feeds,” these are the missing capabilities:

### 1) Extract split ratio (required for real planning)
Ratio is not currently extracted from NASDAQ/SEC/press content.

Add extraction for common phrasings:
- “1-for-10 reverse stock split” / “one-for-ten” / “1:10”
- Store as structured data on the case (e.g., numerator/denominator or a normalized “1-10” string).

### 2) Introduce a position planner (configurable strategy)
Define an explicit planner that decides:
- Which brokers/accounts are eligible
- What pre-split quantity to buy (often “1 share”, but make it configurable)
- Latest safe buy time (consider settlement; weekend/holiday rules)
- What to do when a position already exists (top-up vs skip)

Drive it via config:
- Broker allowlist/denylist
- Per-broker rounding assumptions (issuer policy vs broker behavior)
- Capital limits per case/day

### 3) Case-driven execution and reconciliation
Suggested strategy loop:
1. Intake case (RSS) → create/update case record (idempotent)
2. Resolve policy + ratio + effective date
3. If round-up confirmed and within your risk window:
   - Create buy-plan entries per account
   - Queue orders with deterministic IDs
4. Observe autoRSA outputs:
   - Order confirmations → mark bought per account
   - Holdings refresh → verify position exists (and reconcile discrepancies)
5. After split effective date:
   - Trigger holdings refresh
   - Validate post-split shares
   - Create sell-plan (optional; policy/price/time-based) and execute

### 4) Dedupe rules that prevent repeated automation
Recommended dedupe keys:
- Intake dedupe: `(ticker, effective_date, source_url)` or `(ticker, source_url_hash)`
- Execution dedupe: `(case_id, action, broker, account)` → “do not schedule twice”
- Alert dedupe: keep over-$ monitor dedupe behavior, but move storage behind a shared state store

### 5) Operator safety switches
Full automation should include:
- Global kill switch (`AUTOMATION_ENABLED=false`)
- Broker allowlist/denylist
- Max spend per case/day
- Dry-run mode (post planned commands without executing)
- Case audit trail (what was detected, planned, executed, confirmed)

---

## Concrete “Next Actions” Checklist

Fastest path to a focused centralized assistant:
1. Resolve reminder scheduling duplication (one scheduler only).
2. Quarantine/delete unused duplicate modules: `utils/secondary_alert_parser.py`, `utils/reverse_split_parser.py`, broken `utils/watch_list_manager.py`.
3. Move `split_watchlist.json` into `VOLUMES_DIR/db/` and wrap it in a store class.
4. Unify policy analysis around a single classifier (prefer `utils/helper_api.py`); have `utils/policy_resolver.py` call it.
5. Add split ratio extraction and store it on a new case record.
6. Introduce a case manager that owns intake dedupe, planning, execution scheduling, and reconciliation from autoRSA outputs.
