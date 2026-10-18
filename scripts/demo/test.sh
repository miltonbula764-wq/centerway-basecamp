#!/usr/bin/env bash
set -euo pipefail
# Runs INSIDE the configured devcontainer, with its own Docker daemon and volume.
python3 scripts/demo/test_runtime.py
export CW_DEMO_TLS_TEST=1
python3 scripts/demo/manage.py start --background
cd .centerway-demo/app
export CW_LOCAL_MVP=1 CW_CODESPACES_DEMO=1 PGHOST=127.0.0.1 PGDATABASE=cw_e2e
python3 scripts/mvp/review-database.py
python3 scripts/mvp/review-database.py --operational
python3 e2e/demo-tls.py
curl --fail --silent --show-error --noproxy demo.centerway.test --resolve demo.centerway.test:8443:127.0.0.1 --cacert e2e/private/tls/cert.pem https://demo.centerway.test:8443/auth/v1/health > e2e/logs/demo-tls-health.json
cd e2e
npm ci --ignore-scripts --no-audit --no-fund
npx playwright install --with-deps chromium
NODE_EXTRA_CA_CERTS="$PWD/private/tls/cert.pem" CW_DEMO_BASE_URL=https://demo.centerway.test:8443 npx playwright test --config playwright.demo.config.mjs
cd ../../..
# Stopping/starting containers and frontend must preserve users, goals and operational events.
python3 scripts/demo/persistence-check.py snapshot
python3 scripts/demo/manage.py stop
python3 scripts/demo/manage.py start --background
python3 scripts/demo/persistence-check.py verify
