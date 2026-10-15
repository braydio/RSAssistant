#!/usr/bin/env python3
"""Inventory (and optionally prune) expendable runtime artifacts under VOLUMES_DIR.

Dry-run by default: reports counts, bytes and age per category. Pruning needs
``--prune --older-than-days N`` and only ever touches known expendable files:

* ``db/fidelity_errors/*.html|*.png``  - broker error captures
* ``logs/*.log.<n>``                    - rotated log files
* ``cache/*.tmp``                       - interrupted cache temp files

Databases, WAL/SHM files, holdings/order audit trails, CSV logs, backups and
anything else are never candidates. Symlinks are never followed or deleted and
every path is verified to resolve inside VOLUMES_DIR.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DAY = 86400
_ROTATED_LOG = re.compile(r"\.log\.\d+$")

# category -> (relative dir, predicate on file name, prune candidate?)
CATEGORIES = {
    "error-captures": ("db/fidelity_errors", lambda n: n.endswith((".html", ".png")), True),
    "rotated-logs": ("logs", lambda n: bool(_ROTATED_LOG.search(n)), True),
    "cache-temp": ("cache", lambda n: n.endswith(".tmp"), True),
    "active-logs": ("logs", lambda n: ".log" in n and not _ROTATED_LOG.search(n), False),
    "cache": ("cache", lambda n: not n.endswith(".tmp"), False),
}


@dataclass
class Item:
    category: str
    path: Path
    size: int
    age_days: float
    candidate: bool


def default_volumes_dir() -> Path:
    env = os.getenv("VOLUMES_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[1] / "volumes"


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root)
        return True
    except (OSError, ValueError):
        return False


def scan(volumes: Path, now: float | None = None) -> list[Item]:
    now = time.time() if now is None else now
    root = volumes.resolve()
    items: list[Item] = []
    for category, (rel, matches, candidate) in CATEGORIES.items():
        directory = root / rel
        if directory.is_symlink() or not directory.is_dir() or not _inside(root, directory):
            continue
        with os.scandir(directory) as entries:  # non-recursive: no traversal surprises
            for entry in entries:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                if not matches(entry.name):
                    continue
                stat = entry.stat(follow_symlinks=False)
                items.append(
                    Item(category, Path(entry.path), stat.st_size,
                         max(0.0, (now - stat.st_mtime) / DAY), candidate)
                )
    return items


def prune(volumes: Path, items: list[Item], older_than_days: float, apply: bool) -> list[Item]:
    root = volumes.resolve()
    removed: list[Item] = []
    for item in items:
        if not item.candidate or item.age_days < older_than_days:
            continue
        if item.path.is_symlink() or not _inside(root, item.path):
            continue
        if apply:
            item.path.unlink()
        removed.append(item)
    return removed


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.2f} MB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--volumes-dir", type=Path, default=default_volumes_dir())
    parser.add_argument("--prune", action="store_true", help="delete expendable files (needs --older-than-days)")
    parser.add_argument("--older-than-days", type=float, help="minimum file age for pruning")
    args = parser.parse_args(argv)

    if args.prune and (args.older_than_days is None or args.older_than_days < 1):
        parser.error("--prune requires --older-than-days N with N >= 1")
    if not args.volumes_dir.is_dir():
        print(f"VOLUMES_DIR not found: {args.volumes_dir}", file=sys.stderr)
        return 2

    items = scan(args.volumes_dir)
    print(f"Volumes: {args.volumes_dir.resolve()}")
    for category in CATEGORIES:
        rows = [i for i in items if i.category == category]
        if rows:
            oldest = max(i.age_days for i in rows)
            tag = "candidate" if rows[0].candidate else "protected"
            print(f"  {category:<15} {len(rows):>4} files {_mb(sum(i.size for i in rows)):>10}  oldest {oldest:.0f}d  [{tag}]")

    if not args.prune:
        print("Dry run: nothing deleted. Use --prune --older-than-days N to remove candidates.")
        return 0

    removed = prune(args.volumes_dir, items, args.older_than_days, apply=True)
    for item in removed:
        print(f"  removed {item.path} ({_mb(item.size)}, {item.age_days:.0f}d)")
    print(f"Pruned {len(removed)} files, {_mb(sum(i.size for i in removed))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
