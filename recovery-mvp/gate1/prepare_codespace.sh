#!/usr/bin/env bash
set -euo pipefail
umask 077
ulimit -c 0
# Run only inside the fresh private package directory created by android_ops.
test -f recovery-mvp/api/requirements.txt
test -f recovery-mvp/gate1/android_stream.py
pg17=/usr/lib/postgresql/17/bin/pg_dump
if ! command -v age >/dev/null || ! test -x "$pg17"; then
  # Existing reviewed installer supports Ubuntu24 only; other OS fails closed.
  bash recovery-mvp/gate1/install-ci-tools.sh >/dev/null 2>&1
fi
"$pg17" --version | python3 -c 'import sys; assert sys.stdin.read().startswith("pg_dump (PostgreSQL) 17.")'
command -v age >/dev/null
# Never use a saved remote Docker context or inherited endpoint selector.
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock info >/dev/null 2>&1
python3 -m venv venv
venv/bin/pip install --disable-pip-version-check -q -r recovery-mvp/api/requirements.txt >/dev/null 2>&1
venv/bin/python -c 'import psycopg'
printf '%s\n' '{"status":"codespace_dependencies_ready","postgres_major":17,"docker_local":true}'
