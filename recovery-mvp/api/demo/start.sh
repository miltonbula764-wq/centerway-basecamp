#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Run from a separate terminal; removal of container deletes all synthetic DB data.
state_dir="${CENTERWAY_DEMO_DIR:-$(mktemp -d)}"
container="centerway-l01-demo-${RANDOM}-$$"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
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
"$state_dir/venv/bin/python" api/demo/provision.py "$container" "$port" "$state_dir"
printf 'Private demo state: %s\nAPI: http://127.0.0.1:8080 (synthetic only)\n' "$state_dir"
CENTERWAY_API_CONFIG="$state_dir/config.json" "$state_dir/venv/bin/gunicorn" --chdir api --bind 127.0.0.1:8080 --workers 1 --threads 4 --timeout 30 'app:load_app()'
