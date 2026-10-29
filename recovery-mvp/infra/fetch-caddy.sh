#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source ./versions.env
output="${1:?Supply a private output directory}"
mkdir -p "$output"
container="$(docker create "$CADDY_IMAGE")"
trap 'docker rm "$container" >/dev/null 2>&1 || true' EXIT
docker cp "$container:/usr/bin/caddy" "$output/caddy"
chmod 0700 "$output/caddy"
"$output/caddy" version
