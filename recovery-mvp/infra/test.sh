#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Mandatory original 67 checks, unchanged.
if [ "${1:-}" != "--tls-only" ]; then ./api/test.sh; fi
state="$(mktemp -d)"
trap 'rm -rf "$state"' EXIT
python3 -m venv "$state/venv"
"$state/venv/bin/pip" install -q -r api/requirements.txt
./infra/fetch-caddy.sh "$state" > "$state/caddy-version.txt"
CENTERWAY_TEST_CADDY="$state/caddy" "$state/venv/bin/python" -B -m unittest discover -s infra/tests -v
