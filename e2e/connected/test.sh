#!/usr/bin/env bash
set -euo pipefail
# Run after e2e/start_backend.py on an empty disposable database; never source .env.
mkdir -p e2e/private e2e/logs
openssl req -x509 -newkey rsa:2048 -nodes -keyout e2e/private/ingestion-key.pem -out e2e/private/ingestion-cert.pem -days 1 -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1' >e2e/logs/connected-tls.log 2>&1
NODE_EXTRA_CA_CERTS="$PWD/e2e/private/ingestion-cert.pem" bun run e2e/connected/run.ts "$@"
