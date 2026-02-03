#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /path/to/auto-rsa" >&2
  exit 1
fi

auto_rsa_dir="$1"
patch_file="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/patches/auto-rsa-holdings.patch"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
default_env_file="$repo_root/config/.env"
auto_rsa_env_file="${AUTO_RSA_ENV_FILE:-$auto_rsa_dir/.env}"

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

auto_rsa_holdings_file="${AUTO_RSA_HOLDINGS_FILE:-}"

if [[ -z "$auto_rsa_holdings_file" ]]; then
  env_file="${ENV_FILE:-$default_env_file}"
  if [[ -f "$env_file" ]]; then
    auto_rsa_holdings_file="$(awk -F= '/^[[:space:]]*AUTO_RSA_HOLDINGS_FILE=/ {print $2}' "$env_file" | tail -n 1 | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//')"
  fi
fi

if [[ -n "$auto_rsa_holdings_file" ]]; then
  if [[ -f "$auto_rsa_env_file" ]]; then
    if grep -qE '^[[:space:]]*AUTO_RSA_HOLDINGS_FILE=' "$auto_rsa_env_file"; then
      sed -i.bak "s|^[[:space:]]*AUTO_RSA_HOLDINGS_FILE=.*|AUTO_RSA_HOLDINGS_FILE=${auto_rsa_holdings_file}|" "$auto_rsa_env_file"
      rm -f "${auto_rsa_env_file}.bak"
    else
      printf '\nAUTO_RSA_HOLDINGS_FILE=%s\n' "$auto_rsa_holdings_file" >> "$auto_rsa_env_file"
    fi
  else
    printf 'AUTO_RSA_HOLDINGS_FILE=%s\n' "$auto_rsa_holdings_file" > "$auto_rsa_env_file"
  fi
  echo "Set AUTO_RSA_HOLDINGS_FILE in $auto_rsa_env_file"
else
  echo "AUTO_RSA_HOLDINGS_FILE not set; add it to auto-rsa env manually."
fi

echo "Applied auto-rsa holdings patch to $auto_rsa_dir"
