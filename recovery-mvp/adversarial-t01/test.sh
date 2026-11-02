#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
state="$(mktemp -d)"
container="centerway-t01-${RANDOM}-$$"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true; rm -rf "$state"' EXIT
python3 -m venv "$state/venv"
"$state/venv/bin/pip" install -q -r api/requirements.txt
password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker run -d --name "$container" -e POSTGRES_PASSWORD="$password" -p 127.0.0.1::5432 postgres:17-alpine >/dev/null
for attempt in {1..60}; do
 if docker exec "$container" sh -c 'test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres' >/dev/null 2>&1; then break; fi
 sleep 1
done
for migration in sql/*.sql; do docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres < "$migration" >/dev/null; done
port="$(docker port "$container" 5432/tcp | cut -d: -f2)"
# Configure actual local PostgreSQL TLS, verified with the generated test CA.
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost' -keyout "$state/key.pem" -out "$state/ca.pem" >/dev/null 2>&1
docker cp "$state/key.pem" "$container:/var/lib/postgresql/server.key" >/dev/null
docker cp "$state/ca.pem" "$container:/var/lib/postgresql/server.crt" >/dev/null
docker exec -u root "$container" sh -c 'chown postgres:postgres /var/lib/postgresql/server.* && chmod 600 /var/lib/postgresql/server.*'
docker exec "$container" psql -U postgres -c "ALTER SYSTEM SET ssl=on" >/dev/null
docker exec "$container" psql -U postgres -c "ALTER SYSTEM SET ssl_cert_file='/var/lib/postgresql/server.crt'" >/dev/null
docker exec "$container" psql -U postgres -c "ALTER SYSTEM SET ssl_key_file='/var/lib/postgresql/server.key'" >/dev/null
docker restart "$container" >/dev/null
for attempt in {1..60}; do
 if docker exec "$container" sh -c 'test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres' >/dev/null 2>&1; then break; fi
 sleep 1
done
port="$(docker port "$container" 5432/tcp | cut -d: -f2)"
CW_HTTP_CONTAINER="$container" CW_HTTP_PORT="$port" CW_HTTP_STATE="$state" "$state/venv/bin/python" -B -m unittest discover -s adversarial-t01/tests -v
