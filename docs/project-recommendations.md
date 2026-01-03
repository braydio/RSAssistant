# RSAssistant Project Review and Recommendations

## Current Snapshot
- Runtime entrypoint: `RSAssistant.py` delegates to `rsassistant/bot/core.py`.
- Core logic lives in `rsassistant/` (cogs, tasks) but most behavior is still in
  `utils/` (message parsing, policy analysis, scheduling, watchlists).
- Optional plugin loading exists via `ENABLED_PLUGINS` and `plugins/`.
- Configuration is centralized in `config/.env` (with `config/.env.example` as
  template) plus a legacy `config/settings.yml`.

## Newcomer Experience: What Is Confusing
1. Two parallel homes for logic (`rsassistant/` vs `utils/`) without a clear
   boundary or ownership model.
2. Split watch state persists to `split_watchlist.json` at repo root, while
   other runtime state lives under `config/` or `volumes/`.
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
  utilities (especially `utils/on_message_utils.py` and `utils/parsing_utils.py`).
- The current structure reads as "mid-migration": you can see the modular bot,
  but the code still reflects the monolith's utility-first organization.

## Recommendations (Prioritized)

### 1) Clarify module ownership (high impact, low risk)
Decide and document a single rule such as:
- `rsassistant/` owns orchestration and Discord I/O
- `utils/` only hosts pure helpers with no Discord context

Then move any Discord-context utilities (for example, parts of
`utils/on_message_utils.py`) under `rsassistant/` so the separation is obvious.

### 2) Centralize runtime state (high impact, medium risk)
Move `split_watchlist.json` under `VOLUMES_DIR/db/` and document it alongside
the other runtime data. Keep operator-edited config under `config/`.

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
  is set
- Action taken (watchlist + autobuy)

### 5) Make `externalization-staging/` explicit or remove it (medium impact)
If it is still a staging area, document it in one place (short README in that
folder). If not, remove it to avoid confusion.

## Suggested Next Steps
1. Create a "Architecture Overview" section in `README.md` with a simple
   bullet diagram (entrypoint -> cogs -> utils/services -> persistence).
2. Define where new code should live (rsassistant vs utils) and add a short
   "Contributing" note in `AGENTS.md` or `README.md`.
3. Move split watch state into `VOLUMES_DIR/db/` and update references.
4. Add a plugin entrypoint module for ULT-MA or adjust loader path.

## Notes for New Contributors
- Start with `rsassistant/bot/core.py` and `utils/on_message_utils.py` to
  understand the runtime flow.
- Configuration is controlled through `config/.env` using
  `config/.env.example` as the template.
