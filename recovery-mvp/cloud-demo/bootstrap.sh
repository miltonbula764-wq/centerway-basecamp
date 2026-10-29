#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
state="${1:?Provide a NEW absolute private state directory}"
case "$state" in /*) ;; *) echo 'Absolute state directory required' >&2; exit 1;; esac
[ ! -e "$state" ] && [ ! -L "$state" ] || { echo 'Refusing existing state' >&2; exit 1; }
python3 - "$state" <<'PYCODE'
import sys
from pathlib import Path
state=Path(sys.argv[1]).resolve()
checkout=Path.cwd().parent
if checkout == state or checkout in state.parents or any(c.isspace() for c in str(state)):
    raise SystemExit('State must be outside checkout, without whitespace')
PYCODE
umask 077
mkdir -m 0700 "$state"
python3 -m venv "$state/venv"
"$state/venv/bin/pip" install -q -r api/requirements.txt
./infra/fetch-caddy.sh "$state/bin"
"$state/venv/bin/python" -B cloud-demo/runtime.py init --state "$state" --caddy "$state/bin/caddy"
echo 'Prepared only on loopback. Start serve explicitly; credentials remain in private state.'
