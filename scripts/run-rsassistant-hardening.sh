#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Not inside a git repository." >&2
  exit 2
}
cd "$ROOT"

MANIFEST="docs/task-packets/rsassistant-hardening/MANIFEST.md"
PACKET_DIR="docs/task-packets/rsassistant-hardening"
WORK_BRANCH="${RSASSISTANT_HARDENING_BRANCH:-codex/rsassistant-hardening}"
CODEX_BIN="${CODEX_BIN:-codex}"

if [[ ! -f "$MANIFEST" ]]; then
  echo "Missing $MANIFEST" >&2
  exit 2
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree must be clean before starting the hardening workstream." >&2
  exit 2
fi

if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
  echo "Codex CLI not found: $CODEX_BIN" >&2
  exit 2
fi

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "$WORK_BRANCH" ]]; then
  if git show-ref --verify --quiet "refs/heads/$WORK_BRANCH"; then
    git switch "$WORK_BRANCH"
  else
    git switch -c "$WORK_BRANCH"
  fi
fi

next_packet() {
  sed -n 's/^- \[ \] `\([^`]*\)`.*/\1/p' "$MANIFEST" | head -n 1
}

while packet="$(next_packet)" && [[ -n "$packet" ]]; do
  packet_path="$PACKET_DIR/$packet"
  if [[ ! -f "$packet_path" ]]; then
    echo "Manifest references missing packet: $packet_path" >&2
    exit 3
  fi

  before="$(git rev-parse HEAD)"
  echo
  echo "==> Running $packet at $before"

  prompt="Execute exactly one bounded RSAssistant hardening packet.

Repository root: $ROOT
Read AGENTS.md.
Read $MANIFEST.
The only implementation packet for this invocation is $packet_path.

Follow the manifest protocol exactly.
Do not audit the repository.
Do not read or implement later packets.
Implement this packet completely, run its focused validation plus the required global validation, mark only this packet complete in MANIFEST.md, commit using the packet's specified commit message, then stop.
If blocked, make no speculative workaround and return a concise blocker report."

  "$CODEX_BIN" exec "$prompt"

  after="$(git rev-parse HEAD)"
  if [[ "$after" == "$before" ]]; then
    echo "Codex returned without creating the required packet commit. Stopping." >&2
    exit 4
  fi

  if grep -Fq -- "- [ ] `$packet`" "$MANIFEST"; then
    echo "Packet was not marked complete in MANIFEST.md. Stopping." >&2
    exit 5
  fi

  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Packet left an uncommitted working tree. Stopping before the next packet." >&2
    git status --short
    exit 6
  fi

  echo "<== Completed $packet at $after"
done

echo
echo "All RSAssistant hardening packets are complete on branch $(git branch --show-current)."
echo "Review the commit series before merging or pushing."
