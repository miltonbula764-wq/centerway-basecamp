#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
state="$(mktemp -d)"
trap 'rm -rf "$state"' EXIT
python3 -m venv "$state/venv"
"$state/venv/bin/pip" install -q -r api/requirements.txt playwright==1.62.0
if [ -z "${CENTERWAY_CHROMIUM_EXECUTABLE:-}" ]; then
 "$state/venv/bin/python" -m playwright install --with-deps chromium
fi
./infra/fetch-caddy.sh "$state/bin" > "$state/caddy-version.txt"
CENTERWAY_TEST_CADDY="$state/bin/caddy" "$state/venv/bin/python" -B -m unittest discover -s manual/tests -v
