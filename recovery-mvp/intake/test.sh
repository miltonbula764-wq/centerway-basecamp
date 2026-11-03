#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Pure deterministic tests: no network, tokens, database or external SaaS.
python3 -B -m unittest discover -s intake/tests -v

# Disposable PostgreSQL 17 test for real session_user/RLS/security definer.
container="centerway-m01-$RANDOM-$$"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$container" -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine >/dev/null
ready=false
for i in {1..40}; do
  if docker exec "$container" sh -c 'test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres' >/dev/null 2>&1; then
    ready=true; break
  fi
  sleep 1
done
[ "$ready" = true ] || { echo "Disposable PostgreSQL failed to start" >&2; exit 1; }

# Keep F01-F06 migrations pristine; add M01 in the isolated test database.
for migration in sql/*.sql; do
  docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres < "$migration" >/dev/null
done
docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres < intake/001_posthog_outcome_intake.sql >/dev/null

docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres >/dev/null <<'SQL'
CREATE ROLE m01_a LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS IN ROLE centerway_api;
CREATE ROLE m01_b LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS IN ROLE centerway_api;
INSERT INTO centerway.companies(tenant_id,name)
VALUES ('a1000000-0000-0000-0000-000000000001','SYNTHETIC SaaS A'),
       ('b1000000-0000-0000-0000-000000000001','SYNTHETIC SaaS B');
INSERT INTO centerway.memberships(principal,tenant_id)
VALUES ('m01_a','a1000000-0000-0000-0000-000000000001'),
       ('m01_b','b1000000-0000-0000-0000-000000000001');
SQL

docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres < intake/sql_access_test.sql >/dev/null
echo "M01 source, replay and PostgreSQL tenancy checks passed."
