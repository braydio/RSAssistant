"""One-time migration entrypoint for legacy JSON state.

This script imports legacy account mapping, watchlist, and sell-list JSON files
into SQL tables and optionally archives the original JSON files.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the migration runner."""

    parser = argparse.ArgumentParser(
        description="Migrate legacy account/watch/sell JSON files into SQLite tables."
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Rename successfully migrated JSON files with a .migrated suffix.",
    )
    return parser.parse_args()


def main() -> int:
    """Run the legacy JSON to SQL migration."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    from utils.sql_utils import init_db, migrate_legacy_json_data

    init_db()
    results = migrate_legacy_json_data(remove_legacy_files=args.archive)
    logger.info(
        "Migration finished: account_mappings=%s watchlist=%s sell_list=%s",
        results["account_mappings"],
        results["watchlist"],
        results["sell_list"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
