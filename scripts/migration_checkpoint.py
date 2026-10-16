#!/usr/bin/env python3
"""Read-only inventory and WAL-consistent SQLite backup for RSAssistant migration.

Never opens the source database for writing or imports application runtime code.
Database backups contain financial/account information: store them privately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import subprocess
import sys
from datetime import datetime, timezone

TABLES = ("Accounts", "holdings_current", "HoldingsLive", "OrderHistory",
          "rsa_order_send_log", "split_monitor", "split_event_intents")


def source_connection(source: Path) -> sqlite3.Connection:
    if source.is_symlink() or not source.is_file():
        raise ValueError("source must be an existing regular SQLite file, not a symlink")
    conn = sqlite3.connect(source.resolve(strict=True).as_uri() + "?mode=ro", uri=True, timeout=10)
    conn.execute("PRAGMA query_only=ON")
    return conn


def inventory(conn: sqlite3.Connection) -> dict:
    check = conn.execute("PRAGMA quick_check").fetchone()[0]
    if check != "ok":
        raise ValueError("SQLite quick_check failed")
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    available = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    counts = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
              for table in TABLES if table in available}
    return {"schema_version": version, "quick_check": check, "row_counts": counts}


def git_state(root: Path) -> dict:
    def git(*args: str) -> str:
        try:
            return subprocess.check_output(["git", "-C", str(root), *args],
                                           stderr=subprocess.DEVNULL, timeout=5, text=True).strip()
        except (OSError, subprocess.SubprocessError):
            return "unavailable"
    revision = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"head": revision, "tracked_worktree_clean": status == "" if status != "unavailable" else None}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def private_destination(directory: Path, source: Path) -> Path:
    if directory.is_symlink():
        raise ValueError("backup destination must not be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) & 0o077:
        raise ValueError("backup destination directory must have mode 0700")
    if directory.resolve() == source.resolve().parent:
        raise ValueError("backup destination must differ from source database directory")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return directory / f"rsa-checkpoint-{timestamp}-{secrets.token_hex(4)}.sqlite3"


def backup(source: Path, directory: Path, root: Path) -> dict:
    """Use SQLite's online backup API, not a direct copy of a live WAL database."""
    with source_connection(source) as original:
        initial = inventory(original)
        target = private_destination(directory, source)
        tmp = target.with_suffix(".partial")
        descriptor = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            with sqlite3.connect(tmp) as destination:
                original.backup(destination, pages=100, sleep=0.05)
            with source_connection(tmp) as confirmed:
                result = inventory(confirmed)
            if result["schema_version"] != initial["schema_version"]:
                raise ValueError("schema changed during backup; rerun checkpoint")
            os.replace(tmp, target)
            os.chmod(target, 0o600)
            manifest = {"format": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                        "file": target.name, "sha256": sha256_file(target),
                        "inventory": result, "git": git_state(root)}
            metadata = target.with_suffix(".json")
            fd = os.open(metadata, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, indent=2, sort_keys=True)
            return {"backup": str(target), "manifest": str(metadata), "inventory": result,
                    "git": manifest["git"]}
        finally:
            if tmp.exists():
                tmp.unlink()


def verify(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("backup must be an existing regular file")
    manifest_path = path.with_suffix(".json")
    if manifest_path.is_symlink():
        raise ValueError("manifest must not be a symlink")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("file") != path.name or manifest.get("sha256") != sha256_file(path):
        raise ValueError("backup checksum or manifest filename mismatch")
    with source_connection(path) as conn:
        result = inventory(conn)
    if result != manifest.get("inventory"):
        raise ValueError("backup inventory differs from manifest")
    return {"verified": True, "inventory": result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("inspect", "backup", "verify"))
    parser.add_argument("--source", type=Path, help="explicit database path (for inspect/backup)")
    parser.add_argument("--dest", type=Path, help="private directory for backups (backup only)")
    parser.add_argument("--backup", type=Path, help="backup file to verify")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        if args.mode == "verify":
            if args.backup is None:
                parser.error("verify requires --backup")
            result = verify(args.backup)
        else:
            if args.source is None:
                parser.error(f"{args.mode} requires --source")
            if args.mode == "inspect":
                with source_connection(args.source) as conn:
                    result = {"inventory": inventory(conn), "git": git_state(args.repo)}
            else:
                if args.dest is None:
                    parser.error("backup requires --dest")
                result = backup(args.source, args.dest, args.repo)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"checkpoint failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
