#!/usr/bin/env python3
"""One-time helper to migrate old config files from volumes/config -> config.

This script copies known configuration files from `volumes/config` into
the unified `config` directory. It skips files that already exist in
`config` unless `--overwrite` is provided.

Usage:
  python scripts/migrate_config.py            # copy missing files only
  python scripts/migrate_config.py --dry-run  # show what would be copied
  python scripts/migrate_config.py --overwrite

Safe to run multiple times.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "volumes" / "config"
NEW = ROOT / "config"

# Known config files that may exist in old location
KNOWN = [
    ".env",
    "settings.yml",
    "account_mapping.json",
    "watch_list.json",
    "sell_list.json",
    "ignore_tickers.txt",
    "ignore_brokers.txt",
    "tagged_alerts.txt",
    "overdollar_actions.json",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate config files to ./config")
    parser.add_argument("--dry-run", action="store_true", help="Only print actions")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files in ./config",
    )
    args = parser.parse_args()

    if not OLD.exists():
        print(f"No old directory found: {OLD}")
        return 0

    NEW.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    for name in KNOWN:
        src = OLD / name
        dst = NEW / name
        if not src.exists():
            continue
        if dst.exists() and not args.overwrite:
            print(f"skip exists: {dst}")
            skipped += 1
            continue
        if args.dry_run:
            print(f"would copy: {src} -> {dst}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            print(f"copied: {src} -> {dst}")
            copied += 1

    print(f"done. copied={copied} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

