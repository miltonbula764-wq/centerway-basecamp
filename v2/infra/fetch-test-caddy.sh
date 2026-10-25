#!/usr/bin/env bash
# QA tool only. No service installation, configuration or publication.
set -euo pipefail
if [[ $# != 1 || "$1" != /* || "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'Usage: fetch-test-caddy.sh /absolute/test-tool-directory (Linux x86_64)' >&2
  exit 2
fi
cw_tool_dir="$1"
cw_archive='caddy_2.11.7_linux_amd64.tar.gz'
cw_sha512='a7a433a1b133efc3c8d10eb0b99d52a24b5ef5c322dc77f5282182b1c0402139ab83f3a99f0c52409df77d20123fb0b523edad8a66d8f5e49136197bf61ef0e7'
mkdir -p "$cw_tool_dir"
if [[ -e "$cw_tool_dir/caddy" ]]; then
  echo 'Refusing to replace an existing QA tool' >&2
  exit 1
fi
cw_download_dir="$(mktemp -d)"
trap 'rm -rf "$cw_download_dir"' EXIT
curl --fail --location --silent --show-error --connect-timeout 15 --max-time 90 \
  "https://github.com/caddyserver/caddy/releases/download/v2.11.7/$cw_archive" \
  --output "$cw_download_dir/$cw_archive"
(cd "$cw_download_dir"; printf '%s  %s\n' "$cw_sha512" "$cw_archive" | sha512sum --check --status)
tar --extract --gzip --file "$cw_download_dir/$cw_archive" --directory "$cw_download_dir" caddy
install -m 0755 "$cw_download_dir/caddy" "$cw_tool_dir/caddy"
"$cw_tool_dir/caddy" version
