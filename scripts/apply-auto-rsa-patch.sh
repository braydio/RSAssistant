#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--check] [--state-file PATH] /path/to/auto-rsa" >&2
}

check_only=false
state_file=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      check_only=true
      shift
      ;;
    --state-file)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      state_file="$2"
      shift 2
      ;;
    -*)
      usage
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

[[ $# -eq 1 ]] || { usage; exit 2; }

auto_rsa_dir="$(cd "$1" && pwd)"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
patch_file="$repo_root/patches/auto-rsa-holdings.patch"
default_env_file="$repo_root/config/.env"
auto_rsa_env_file="${AUTO_RSA_ENV_FILE:-$auto_rsa_dir/.env}"
state_file="${state_file:-${AUTO_RSA_PATCH_STATE_FILE:-$repo_root/volumes/db/auto_rsa_patch_state.json}}"

[[ -f "$patch_file" ]] || { echo "Patch file not found: $patch_file" >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo "git is required to apply the patch." >&2; exit 1; }

target_relative=""
for candidate in src/helper_api.py helper_api.py src/helperAPI.py helperAPI.py; do
  if [[ -f "$auto_rsa_dir/$candidate" ]]; then
    target_relative="$candidate"
    break
  fi
done
[[ -n "$target_relative" ]] || {
  echo "helper_api.py/helperAPI.py not found in $auto_rsa_dir/src or $auto_rsa_dir" >&2
  exit 1
}

effective_patch="$patch_file"
temp_patch=""
if [[ "$target_relative" != "src/helper_api.py" ]]; then
  temp_patch="$(mktemp)"
  sed \
    -e "s|a/src/helper_api.py|a/$target_relative|g" \
    -e "s|b/src/helper_api.py|b/$target_relative|g" \
    "$patch_file" > "$temp_patch"
  effective_patch="$temp_patch"
fi
trap '[[ -z "$temp_patch" ]] || rm -f "$temp_patch"' EXIT

git_apply=(git -c "safe.directory=$auto_rsa_dir" -C "$auto_rsa_dir" apply)

patch_status=""
if "${git_apply[@]}" --reverse --check "$effective_patch" >/dev/null 2>&1; then
  patch_status="healthy"
elif "${git_apply[@]}" --check "$effective_patch" >/dev/null 2>&1; then
  patch_status="missing"
else
  echo "Auto-rsa holdings patch is neither applied nor cleanly applicable at $auto_rsa_dir." >&2
  echo "The upstream helper API likely changed and the patch must be regenerated." >&2
  exit 1
fi

if $check_only; then
  [[ "$patch_status" == "healthy" ]] || exit 3
  echo "Auto-rsa holdings patch is healthy at $auto_rsa_dir"
  exit 0
fi

if [[ "$patch_status" == "missing" ]]; then
  "${git_apply[@]}" "$effective_patch"
  echo "Reapplied auto-rsa holdings patch to $auto_rsa_dir"
else
  echo "Auto-rsa holdings patch is already healthy at $auto_rsa_dir"
fi

auto_rsa_holdings_file="${AUTO_RSA_HOLDINGS_FILE:-}"
if [[ -z "$auto_rsa_holdings_file" ]]; then
  env_file="${ENV_FILE:-$default_env_file}"
  if [[ -f "$env_file" ]]; then
    auto_rsa_holdings_file="$(awk -F= '/^[[:space:]]*AUTO_RSA_HOLDINGS_FILE=/ {print $2}' "$env_file" | tail -n 1 | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//')"
  fi
fi

if [[ -n "$auto_rsa_holdings_file" ]]; then
  if [[ -f "$auto_rsa_env_file" ]] && grep -qE '^[[:space:]]*AUTO_RSA_HOLDINGS_FILE=' "$auto_rsa_env_file"; then
    sed -i.bak "s|^[[:space:]]*AUTO_RSA_HOLDINGS_FILE=.*|AUTO_RSA_HOLDINGS_FILE=${auto_rsa_holdings_file}|" "$auto_rsa_env_file"
    rm -f "${auto_rsa_env_file}.bak"
  else
    printf '\nAUTO_RSA_HOLDINGS_FILE=%s\n' "$auto_rsa_holdings_file" >> "$auto_rsa_env_file"
  fi
  echo "Set AUTO_RSA_HOLDINGS_FILE in $auto_rsa_env_file"
fi

mkdir -p "$(dirname "$state_file")"
printf '{"auto_rsa_dir":"%s","target":"%s"}\n' "$auto_rsa_dir" "$target_relative" > "$state_file.tmp"
mv "$state_file.tmp" "$state_file"
echo "Recorded auto-rsa patch state in $state_file"
