#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Independent HTTP DB; prior engine suites retain their own isolated lifecycle.
if [ "${1:-}" != "--http-only" ]; then ./tests/run-f03.sh; fi
state_dir="$(mktemp -d)"
container="centerway-l01-test-${RANDOM}-$$"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true; rm -rf "$state_dir"' EXIT
python3 -m venv "$state_dir/venv"
"$state_dir/venv/bin/pip" install -q -r api/requirements.txt
admin_password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker run -d --name "$container" -e POSTGRES_PASSWORD="$admin_password" -p 127.0.0.1::5432 postgres:17-alpine >/dev/null
ready=false
for attempt in {1..30}; do
 if docker exec "$container" sh -c 'test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres' >/dev/null 2>&1; then ready=true; break; fi
 sleep 1
done
[ "$ready" = true ] || exit 1
for migration in sql/*.sql; do docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres < "$migration" >/dev/null; done
port="$(docker port "$container" 5432/tcp | cut -d: -f2)"
CW_HTTP_CONTAINER="$container" CW_HTTP_PORT="$port" CW_HTTP_STATE="$state_dir" "$state_dir/venv/bin/python" -B -m unittest discover -s api/tests -v
