# RSAssistant Externalization and Focus Process

This document outlines the practical steps to refocus the repository on core reverse-split monitoring and order execution while staging optional services for relocation into dedicated plugin-style repositories. The process follows the prior review recommendations and uses a temporary root-level staging directory to hold components before they are migrated elsewhere.

## Goals
- Keep the core repo limited to reverse-split monitoring, watchlist management, holdings audits, and autoRSA order execution.
- Offload optional or dev-ops services (e.g., automated trading, PR watcher, DeepSource monitor, one-off migrations, custom overrides) into separate plugin or utility repos.
- Preserve history and traceability by using a staging area and tagged releases during the transition.

## Staging Directory
- Create `externalization-staging/` at the repository root to temporarily house modules that will move to focused repositories.
- Within the staging directory, mirror the target structure for each outbound component so that `git mv` preserves history during migration.
- Use `externalization-staging/MANIFEST.md` (created in this change) as the authoritative list of what should be parked in staging and which destination repo will own it.

## Step-by-Step Process
1. **Baseline tagging**
   - Tag the current state before extraction (for example, `v-current-monolith`) so consumers can pin the pre-modular release.

2. **Create staging area**
   - Ensure `externalization-staging/` exists.
   - For each optional component, create a matching subdirectory inside `externalization-staging/` that reflects the destination layout (examples below). This enables `git mv` to track history when the new repos are initialized.

3. **Move optional components into staging**
   - Use `git mv` to relocate the following into `externalization-staging/`:
     - `utils/trading/` → `externalization-staging/plugins/ultma/` (future `rsassistant-ultma-plugin`)
     - `pr_watcher.py` → `externalization-staging/devops/pr_watcher.py` (future `rsassistant-devops`)
     - `deepsource_monitor.py` → `externalization-staging/devops/deepsource_monitor.py` (future `rsassistant-devops`)
     - `scripts/migrate_config.py` → `externalization-staging/scripts/migrate_config.py` (future `rsassistant-maintenance-scripts`)
     - `custom-overrides/` → `externalization-staging/custom-overrides/` (future `auto-rsa-overrides` or submodule)
   - Leave core reverse-split files (`RSAssistant.py`, `utils/watch_utils.py`, `utils/split_watch_utils.py`, `utils/on_message_utils.py`, `utils/order_exec.py`, logging/persistence utilities) in place.

4. **Version core repo**
   - After staging the optional components, run the full test suite to confirm the core remains functional.
   - Tag the focused core release (for example, `v-core-only`) after ensuring commands and monitoring paths still work without optional modules.

5. **Spin out focused repositories**
   - Initialize new repositories for each staged component using `externalization-staging/` as the source so that Git history is preserved via subtree split or filter-repo.
   - Suggested repo mapping:
     - `externalization-staging/plugins/ultma/` → `rsassistant-ultma-plugin`
     - `externalization-staging/devops/` → `rsassistant-devops`
     - `externalization-staging/scripts/` → `rsassistant-maintenance-scripts`
     - `externalization-staging/custom-overrides/` → `auto-rsa-overrides` (or a dedicated fork/submodule)

6. **Reconnect via plugins**
   - Replace direct imports with plugin hooks that load optional features only when present (for example, `ENABLED_PLUGINS=ultma`).
   - Document installation steps for each optional repo and update `requirements.txt` or extras to reference them as optional dependencies.

7. **Retire the staging directory**
   - Once outbound repos are initialized and referenced as plugins, remove the staged copies from this repository to complete the focus effort.

## Operational Checklist
- [ ] Tag current monolithic state (e.g., `v-current-monolith`).
- [ ] Create/verify `externalization-staging/` and its subfolders.
- [ ] Move optional components into staging using `git mv`.
- [ ] Run `python -m unittest discover -s unittests -p '*_test.py'` on the focused codebase.
- [ ] Tag focused core release (e.g., `v-core-only`).
- [ ] Initialize outbound repositories from staged components.
- [ ] Wire plugin loading into the core bot and update documentation.
- [ ] Delete staging content after plugin repos are active.
