#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" != "--persistent-only" ]; then ./infra/test.sh; fi
state="$(mktemp -d)"
trap 'rm -rf "$state"' EXIT
python3 -m venv "$state/venv"
"$state/venv/bin/pip" install -q -r api/requirements.txt
./infra/fetch-caddy.sh "$state/bin" > "$state/caddy-version.txt"
CENTERWAY_TEST_CADDY="$state/bin/caddy" "$state/venv/bin/python" -B -m unittest discover -s cloud-demo/tests -v
