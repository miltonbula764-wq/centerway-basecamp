#!/usr/bin/env bash
set -euo pipefail
umask 077
ulimit -c 0
# Single entry point on the owner's Android; never executed by remote CI.
command -v pkg >/dev/null
if [[ "${1:-}" == diagnose ]]; then
  cd "$(dirname "$0")/../.."
  exec python recovery-mvp/gate1/android_ops.py "$@"
fi
for dependency in python git gh openssh age; do
  case "$dependency" in
    openssh) binary=ssh;;
    *) binary="$dependency";;
  esac
  if ! command -v "$binary" >/dev/null; then pkg install -y "$dependency"; fi
done
if ! gh auth status >/dev/null 2>&1; then
  # Credentials must not be changed implicitly by preparation or diagnostics.
  printf '%s\n' 'github_auth_unavailable; credentials_unchanged' >&2
  exit 1
fi
cd "$(dirname "$0")/../.."
exec python recovery-mvp/gate1/android_ops.py "$@"
