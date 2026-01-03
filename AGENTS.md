# Repository Guidelines

## Project Structure & Modules
- `RSAssistant.py`: main entrypoint for the assistant/bot.
- `utils/`: reusable modules (config, parsing, orders, cache, I/O).
- `externalization-staging/`: staged plugins/utilities slated for extraction.
- `unittests/`: unit tests grouped by feature (e.g., `*_test.py`).
- `config/`: single source for settings and `.env`.
- `volumes/`: docker-mounted db/excel/logs data.
- Docker: `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`.

## Build, Test, and Dev Commands
- Setup venv: `python -m venv .venv && source .venv/bin/activate`
- Install deps: `pip install -r requirements.txt`
- Run app: `python RSAssistant.py`
- Run PR watcher: `python externalization-staging/devops/pr_watcher.py`
- Run tests: `python -m unittest discover -s unittests -p '*_test.py'`
- Docker build/run: `docker build -t rsassistant .` then `docker compose up`

## Coding Style & Naming
- Python, PEP 8, 4-space indentation; prefer type hints where reasonable.
- Names: modules/functions `snake_case`, classes `PascalCase`, constants `UPPER_CASE`.
- Keep functions focused; avoid side effects in utilities.
- Logging via `utils/logging_setup.py`; favor structured, redaction-safe logs.

## Testing Guidelines
- Framework: `unittest` (tests in `unittests/`, pattern `*_test.py`).
- Add tests for new features and bug fixes; cover edge cases and I/O boundaries.
- Use deterministic inputs; avoid real network or live broker calls.
- Example: `python -m unittest unittests/order_queue_manager_test.py`

## Commit & Pull Requests
- Commits: use Conventional Commits style when possible (e.g., `feat(config): support custom volumes directory`, `fix(commands): add brokerwith alias`).
- PRs: concise description, link issues, list changes, screenshots/logs for user-visible behavior.
- Required: tests passing, updated docs (README or examples) for user-facing changes.

## Security & Configuration
- Never commit secrets. Copy `config/example.env` to `config/.env` for local dev; Docker reads from `config/.env`.
- Primary app settings: `config/.env` (with `ENV_FILE` overrides). `config/settings.yml` is legacy/compat.
- Redact tokens and account identifiers in logs and PRs.

## Conventions & Examples
- New util: `utils/my_feature_utils.py` with focused functions + tests in `unittests/my_feature_utils_test.py`.
- CLI run with custom config: `ENV_FILE=config/.env python RSAssistant.py`.
