#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
 "") ./cloud-demo/test.sh ;;
 --handoff-only|--generate) ;;
 *) echo "Expected --handoff-only or --generate" >&2; exit 1 ;;
esac
state="$(mktemp -d)"
trap 'rm -rf "$state"' EXIT
python3 -m venv "$state/venv"
"$state/venv/bin/pip" install -q -r integration/requirements.txt
./infra/fetch-caddy.sh "$state/bin" > "$state/caddy-version.txt"
if [ "${1:-}" = "--generate" ]; then
 "$state/venv/bin/python" -B integration/capture.py --caddy "$state/bin/caddy" --write
else
 CENTERWAY_TEST_CADDY="$state/bin/caddy" "$state/venv/bin/python" -B -m unittest discover -s integration/tests -v
fi
