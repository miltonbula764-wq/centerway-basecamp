#!/usr/bin/env bash
set -euo pipefail
npm install --global bun@1.3.0 --registry=https://registry.npmjs.org --no-audit --no-fund
python3 --version
node --version
bun --version
psql --version
printf '%s\n' 'CENTERWAY: ferramentas instaladas. O arranque usa apenas a stack sintética própria.'
