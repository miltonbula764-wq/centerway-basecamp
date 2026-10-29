#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
container="centerway-f03-test-${RANDOM}-$$"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run --name "$container" -d -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine >/dev/null
ready=false
for attempt in {1..30}; do
  # The image's temporary bootstrap server also answers pg_isready. Wait for PID 1
  # to become the final postgres server before applying any migration.
  if docker exec "$container" sh -c 'test "$(cat /proc/1/comm)" = postgres && pg_isready -U postgres' >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [ "$ready" != true ]; then
  echo 'Disposable PostgreSQL did not finish initialization' >&2
  exit 1
fi
for migration in sql/*.sql; do
  docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres < "$migration" >/dev/null
done
CW_TEST_CONTAINER="$container" python3 -B -m unittest discover -s tests -v
