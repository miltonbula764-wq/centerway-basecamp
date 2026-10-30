#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
state="$(mktemp -d)"
trap 'rm -rf "$state"' EXIT
python3 -m venv "$state/venv"
"$state/venv/bin/pip" install -q -r api/requirements.txt playwright==1.62.0
"$state/venv/bin/python" -m playwright install --with-deps chromium
./infra/fetch-caddy.sh "$state/bin" > "$state/caddy-version.txt"
node compatibility/build.mjs "$state/js"
for repetition in 1 2; do
  echo "SYNTHETIC Chromium compatibility: fresh-stack repetition $repetition/2"
  CENTERWAY_TEST_CADDY="$state/bin/caddy" CENTERWAY_TEST_JS="$state/js" \
    "$state/venv/bin/python" -B -m unittest discover -s compatibility/tests -v
done
