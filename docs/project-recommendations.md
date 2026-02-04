# RSAssistant Project Review and Recommendations

## Current Snapshot
- Runtime entrypoint: `RSAssistant.py` delegates to `rsassistant/bot/core.py`.
- Core logic lives in `rsassistant/` (cogs, tasks) but most behavior is still in
  `utils/` (message parsing, policy analysis, scheduling, watchlists).
- Optional plugin loading exists via `ENABLED_PLUGINS` and `plugins/`.
- Configuration is centralized in `config/.env` (with `config/.env.example` as
  template) plus a legacy `config/settings.yml`.
- Excel logging is deprecated; SQL persistence is the source of truth for order
  history, account mappings, and watchlists.

## Newcomer Experience: What Is Confusing
1. Two parallel homes for logic (`rsassistant/` vs `utils/`) without a clear
   boundary or ownership model.
2. Split watch state now persists in SQLite tables alongside the other runtime
   artifacts in `volumes/`.
3. Plugin wiring expects `plugins.<name>.cog`, but `plugins/ultma/` does not
   currently expose that module, so "plugin" feels incomplete.
4. `externalization-staging/` exists but no longer appears in README or other
   docs, which can make its purpose unclear.
5. The policy pipeline mixes local heuristics with LLM parsing and does not
   explicitly document precedence or uncertainty handling in one place.

## Layout and Design Assessment
- Strengths: the modular bot entrypoint is clear and the "core cogs" list in
  `rsassistant/bot/core.py` provides a straightforward runtime path.
- Weaknesses: the "thin cog + heavy utils" design is efficient but makes
  navigation harder because newcomers must jump between cogs and large
  utilities (especially `rsassistant/bot/handlers/on_message.py` and `utils/parsing_utils.py`).
- The current structure reads as "mid-migration": you can see the modular bot,
  but the code still reflects the monolith's utility-first organization.

## Recommendations (Prioritized)

### 1) Clarify module ownership (high impact, low risk)
Decide and document a single rule such as:
- `rsassistant/` owns orchestration and Discord I/O
- `utils/` only hosts pure helpers with no Discord context

Then move any Discord-context utilities (for example, parts of
`rsassistant/bot/handlers/on_message.py`) under `rsassistant/` so the separation is obvious.

### 2) Centralize runtime state (high impact, medium risk)
Keep watchlist and account mapping state in the SQLite database under
`VOLUMES_DIR/db/` and document it alongside the other runtime data. Keep
operator-edited config under `config/`.

### 3) Finish the plugin contract (medium impact, low risk)
Either:
- Add `plugins/ultma/cog.py` (or `plugins/ultma/cog/__init__.py`) with `setup()`,
  or
- Update plugin loading to target the actual module you want as the entrypoint.

This removes the current mismatch and makes plugin usage feel complete.

### 4) Document the policy decision flow (medium impact, low risk)
Write a short "policy decision order" section in README (or a dedicated doc):
- Local parser result
- LLM tie-breaker when local parsing is uncertain and `OPENAI_POLICY_ENABLED`
  is set (and note `PROGRAMMATIC_POLICY_ENABLED=false` disables local parsing)
- Action taken (watchlist + autobuy)

### 5) Make `externalization-staging/` explicit or remove it (medium impact)
If it is still a staging area, document it in one place (short README in that
folder). If not, remove it to avoid confusion.

## Unification Progress
- Completed: moved Discord channel resolution into `rsassistant/bot/channel_resolver.py`,
  updated imports/tests, and removed the `utils/channel_resolver.py` copy so
  bot-facing logic stays within the bot package.
- Completed: moved holdings history Discord helpers into `rsassistant/bot/history_query.py`,
  removing the duplicate `utils/history_query.py` module to keep bot responses
  consolidated under the bot package.
- Completed: removed unused `utils/secondary_alert_parser.py` now that secondary
  channel handling lives in `rsassistant/bot/handlers/on_message.py`.

## Suggested Next Steps
1. Create a "Architecture Overview" section in `README.md` with a simple
   bullet diagram (entrypoint -> cogs -> utils/services -> persistence).
2. Define where new code should live (rsassistant vs utils) and add a short
   "Contributing" note in `AGENTS.md` or `README.md`.
3. Confirm watchlist state and account mappings live in SQLite under
   `VOLUMES_DIR/db/` and update references.
4. Add a plugin entrypoint module for ULT-MA or adjust loader path.
5. Capture the policy decision flow in README or a dedicated doc, outlining
   how local parsing, optional LLM inference, and resulting actions compose the
   final output.

## Implementation Response
- Ownership: We agree that clarifying the boundary between `rsassistant/` and
  `utils/` will simplify onboarding. The plan is to treat `rsassistant/` as the
  Discord-facing layer while keeping `utils/` reserved for pure helpers, then
  move any remaining Discord-context utilities into `rsassistant/`.
- Runtime state: Centralizing artifacts like watchlists and account mappings in
  SQLite under `VOLUMES_DIR/db/` aligns with the deployed data layout and keeps
  versioned config in `config/`. The watchlist tables now share the database
  with order history, so the docs and loader logic should reflect the update.
- Plugins: Completing the plugin contract for ULT-MA (via
  `plugins/ultma/cog.py`) and wiring the `..ultma` command group keeps the
  plugin pipeline consistent and ensures `ENABLED_PLUGINS=ultma` starts the
  optional trading tasks.
- Policies: Added a "Policy Decision Flow" section in `README.md` so the local
  parser → OpenAI fallback → watchlist/autobuy actions order is documented for
  operators.
- Staging folder: Either document the role of `externalization-staging/` in
  `docs/` (noting it is still experimental) or remove it if it is no longer
  needed; the current silence makes it hard to reason about the workspace.

## Next Steps to Implement
1. Add the recommended architecture overview and module ownership note to
   `README.md`, referencing the updated `AGENTS.md` guidance for contributors.
2. Audit `utils/` for any remaining Discord-context logic, migrate those pieces
   into `rsassistant/`, and ensure imports are updated before we start trimming
   unused utilities.
3. Confirm watchlist and account mapping reads/writes use the SQLite tables and
   that the documentation reflects the new persistence path.
4. Verify `ENABLED_PLUGINS=ultma` loads `plugins.ultma.cog` and exposes the
   `..ultma` commands so operators can monitor or force entries as needed.
5. Keep the policy decision flow documentation in sync as the heuristics or LLM
   fallback behavior evolve so the rollout order stays accurate.

## Notes for New Contributors
- Start with `rsassistant/bot/core.py` and `rsassistant/bot/handlers/on_message.py` to
  understand the runtime flow.
- Configuration is controlled through `config/.env` using
  `config/.env.example` as the template.
