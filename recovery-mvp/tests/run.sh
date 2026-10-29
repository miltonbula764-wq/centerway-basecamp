#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# A disposable local database, no published ports and no access to the legacy DB.
container="centerway-f01-test-${RANDOM}-$$"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run --name "$container" -d -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine >/dev/null
for attempt in {1..30}; do
  if docker exec "$container" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
for migration in sql/*.sql; do
  docker exec -i "$container" psql -X -v ON_ERROR_STOP=1 -U postgres < "$migration" >/dev/null
done
CW_TEST_CONTAINER="$container" python3 -B -m unittest discover -s tests -v
