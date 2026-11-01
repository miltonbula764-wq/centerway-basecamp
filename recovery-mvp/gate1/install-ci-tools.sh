#!/usr/bin/env bash
set -euo pipefail
# Ubuntu24 GitHub standard runner: PG17 is not in the default Ubuntu repository.
# Install from the signed PostgreSQL project repository, not an unverified script.
source /etc/os-release
test "$ID" = ubuntu
test "$VERSION_CODENAME" = noble
key_file="$(mktemp)"
trap 'rm -f "$key_file"' EXIT
curl --fail --silent --show-error --location https://www.postgresql.org/media/keys/ACCC4CF8.asc --output "$key_file"
fingerprint="$(gpg --batch --show-keys --with-colons "$key_file" 2>/dev/null | awk -F: '$1 == "fpr" {print $10; exit}')"
test "$fingerprint" = B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8
sudo install -m 0644 "$key_file" /usr/share/keyrings/centerway-pgdg.asc
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/centerway-pgdg.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main' | sudo tee /etc/apt/sources.list.d/centerway-pgdg.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y age postgresql-client-17
/usr/lib/postgresql/17/bin/pg_dump --version
