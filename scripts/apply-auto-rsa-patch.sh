#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/auto-rsa" >&2
  exit 1
fi

auto_rsa_dir="$1"
patch_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/patches/auto-rsa-holdings.patch"

if [[ ! -f "$patch_file" ]]; then
  echo "Patch file not found: $patch_file" >&2
  exit 1
fi

if [[ ! -d "$auto_rsa_dir" ]]; then
  echo "Auto-RSA directory not found: $auto_rsa_dir" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "git is required to apply the patch." >&2
  exit 1
fi

( cd "$auto_rsa_dir" && git apply "$patch_file" )

echo "Applied auto-rsa holdings patch to $auto_rsa_dir"
