# Externalization Staging Manifest

This staging area captures components slated for extraction into focused repositories. Move the items below into the matching paths inside `externalization-staging/` before creating the new repositories. Keep directory names aligned to preserve Git history when using `git mv` and `git subtree split` or `git filter-repo`.

## Components to Stage
- `plugins/ultma/` (from `utils/trading/`)
  - **Destination repo:** `rsassistant-ultma-plugin`
  - **Notes:** Preserve state store and market data helpers; expose a `setup(bot)` entry point for plugin loading.
- `devops/pr_watcher.py` (from `pr_watcher.py`)
  - **Destination repo:** `rsassistant-devops`
  - **Notes:** Keep CI polling interval configurable via environment variables.
- `devops/deepsource_monitor.py` (from `deepsource_monitor.py`)
  - **Destination repo:** `rsassistant-devops`
  - **Notes:** Maintain webhook configuration and environment flags separately from the core bot.
- `scripts/migrate_config.py`
  - **Destination repo:** `rsassistant-maintenance-scripts`
  - **Notes:** Mark clearly as one-time migration tooling.
- `custom-overrides/`
  - **Destination repo:** `auto-rsa-overrides` (or a dedicated fork/submodule)
  - **Notes:** Consider converting to a Git submodule for long-term maintenance.

## Staging Checklist
- [ ] Create the listed subdirectories under `externalization-staging/`.
- [ ] Use `git mv` to move each component into its staged path.
- [ ] Validate imports and update plugin loader paths in the core repo after staging.
- [ ] Run `python -m unittest discover -s unittests -p '*_test.py'` to confirm the focused build passes.
- [ ] Initialize destination repositories from the staged content.
- [ ] Remove staged content from this repo once plugin dependencies are documented.
