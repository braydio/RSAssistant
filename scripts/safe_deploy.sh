#!/usr/bin/env bash
# Guarded replacement for the `redocker` alias (docker compose down && up --build).
# Refuses to build from a dirty tree or without a fresh verified DB checkpoint.
# Default is a dry run; pass --yes to actually rebuild/recreate.
set -euo pipefail

cd "$(dirname "$0")/.."
BACKUP_DIR="${RSA_CHECKPOINT_DIR:-$HOME/.rsa-backups/checkpoints}"
MAX_AGE_MIN="${RSA_CHECKPOINT_MAX_AGE_MIN:-1440}"
SERVICES=("$@")
APPLY=0
if [[ "${1:-}" == "--yes" ]]; then APPLY=1; SERVICES=("${@:2}"); fi

die() { echo "REFUSING: $*" >&2; exit 1; }

dirty=$(git status --porcelain --untracked-files=no | grep -v 'RSDashboard.local.trash' || true)
[[ -z "$dirty" ]] || die "tracked working tree is dirty:"$'\n'"$dirty"

if [[ -d auto-rsa/.git ]]; then
  nested_dirty=$(git -C auto-rsa status --porcelain --untracked-files=no)
  [[ -z "$nested_dirty" ]] || die "nested auto-rsa has uncommitted tracked changes"
fi

head=$(git rev-parse --short HEAD)
latest=$(find "$BACKUP_DIR" -maxdepth 1 -name 'rsa-checkpoint-*.json' -mmin "-$MAX_AGE_MIN" 2>/dev/null | sort | tail -1)
[[ -n "$latest" ]] || die "no checkpoint newer than ${MAX_AGE_MIN}m in $BACKUP_DIR (run scripts/migration_checkpoint.py backup)"
backup="${latest%.json}.sqlite3"
python scripts/migration_checkpoint.py verify --backup "$backup" >/dev/null || die "checkpoint failed verification: $backup"

running=$(docker inspect rsassistant --format '{{index .Config.Labels "org.rsa.git-rev"}}' 2>/dev/null || true)
echo "deploying commit : $head ($(git log -1 --format=%s))"
echo "auto-rsa commit  : $(git -C auto-rsa rev-parse --short HEAD 2>/dev/null || echo n/a)"
echo "verified backup  : $backup"
echo "last deployed rev: ${running:-unknown (no revision label yet)}"
[[ -n "$running" ]] && git diff --stat "$running" HEAD || true

if [[ $APPLY -ne 1 ]]; then echo "dry run OK; re-run with --yes to deploy"; exit 0; fi

export GIT_REV="$head"
docker compose up -d --build "${SERVICES[@]}"
printf '%s %s %s\n' "$(date -u +%FT%TZ)" "$head" "$(basename "$backup")" >> "$HOME/.rsa-backups/deploys.log"
