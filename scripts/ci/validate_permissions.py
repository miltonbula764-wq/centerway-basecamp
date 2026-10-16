#!/usr/bin/env python3
"""GitHub-hosted CI only. No initdb/pg_ctl: the workflow owns a disposable PG17 service."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['sql', 'drizzle'])
    mode = parser.parse_args().mode
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise SystemExit('Only run in the disposable GitHub-hosted workflow.')
    source = Path(__file__).resolve().parents[2]
    work = Path(os.environ['RUNNER_TEMP']) / 'cw-validation'
    logs = work / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    results = []
    # Whitelist copied inputs: never copy/source .env, .npmrc, app config or real DB URLs.
    shutil.copytree(source / 'drizzle', work / 'drizzle')
    shutil.copytree(source / 'supabase/tests', work / 'supabase/tests')
    shutil.copyfile(source / 'drizzle.config.ts', work / 'drizzle.config.ts')
    db = 'cw_permissions' if mode == 'sql' else 'cw_runner'
    env = os.environ.copy()
    for key in ('PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE', 'PGPASSWORD', 'PGOPTIONS',
                'DATABASE_URL', 'LOVABLE_DB_MIGRATION_URL', 'NODE_OPTIONS', 'NODE_PATH'):
        env.pop(key, None)
    env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='postgres', PGDATABASE=db,
               PGPASSFILE=str(work / 'no-password-file'), PGCONNECT_TIMEOUT='10', PGSSLMODE='disable')
    psql = ['psql', '-X', '-v', 'ON_ERROR_STOP=1']

    def run(name, command, *, allow_error=False, environment=None):
        with (logs / (name + '.log')).open('w') as output:
            proc = subprocess.run(command, cwd=work, env=environment or env,
                                  stdout=output, stderr=subprocess.STDOUT, text=True)
        results.append({'step': name, 'exit_code': proc.returncode})
        (logs / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(f'{name}: exit {proc.returncode}', flush=True)
        text = (logs / (name + '.log')).read_text()
        # Also readable on a phone without downloading GitHub's artifact ZIP.
        print('\n'.join(text.splitlines()[-50:]), flush=True)
        if proc.returncode and not allow_error:
            raise RuntimeError(f'{name} failed; see {name}.log')
        return text

    def query(name, sql):
        return run(name, psql + ['-At', '-c', sql]).strip()

    def sqlfile(name, file, *, transaction=False):
        return run(name, psql + (['--single-transaction'] if transaction else []) + ['-f', file])

    def expect(text, marker):
        if marker not in text:
            raise AssertionError(f'Missing expected marker: {marker}')

    def clean(name):
        if query(name, 'SELECT (SELECT count(*) FROM auth.users), (SELECT count(*) FROM public.tenants)') != '0|0':
            raise AssertionError('Synthetic fixtures persisted after rollback')

    tests = 'supabase/tests/'
    journal_path = work / 'drizzle/migrations/meta/_journal.json'
    journal = json.loads(journal_path.read_text())
    entries = journal['entries']
    if len(entries) != 12 or entries[-1]['tag'] != '0011_restore_client_privileges':
        raise AssertionError('Review expects precisely migrations 0000–0011')
    error = None
    try:
        run('create-database', ['createdb', db])
        version = query('server-version', 'SHOW server_version_num')
        if not 170000 <= int(version) < 180000:
            raise AssertionError('PostgreSQL 17 required')
        sqlfile('bootstrap', tests + 'local_privileges_bootstrap.sql')
        if mode == 'sql':
            for entry in entries[:-1]:
                sqlfile(entry['tag'], 'drizzle/migrations/' + entry['tag'] + '.sql', transaction=True)
            run('clean-catalog', psql + ['-At', '-f', tests + 'client_privileges_catalog.sql'])
            expect(sqlfile('reapply-before', tests + 'client_privileges_reapply_test.sql'), 'CW_REAPPLY_PASS')
            expect(run('correction', psql + ['--single-transaction', '-f',
                       'drizzle/migrations/0011_restore_client_privileges.sql', '-f',
                       tests + 'client_privileges_test.sql']), 'CW_ACL_PASS checks=812')
        else:
            # Avoid Lovable's registry URLs in bun.lock; install only existing tooling versions.
            # Transitive resolutions are captured in package-lock.json for review (not a full app install).
            lock = (source / 'bun.lock').read_text()
            deps = {}
            for package in ('drizzle-kit', 'drizzle-orm', 'postgres'):
                match = re.search(r'"' + re.escape(package) + r'": \["' + re.escape(package) + r'@([^" ]+)"', lock)
                if not match:
                    raise AssertionError(f'Missing exact version of {package} in bun.lock')
                deps[package] = match.group(1)
            (work / 'package.json').write_text(json.dumps({'private': True, 'dependencies': deps}, indent=2))
            npm_env = env.copy()
            # Use a separate home and explicit public npm configuration; no injected registry tokens.
            npm_env['HOME'] = str(work / 'npm-home')
            Path(npm_env['HOME']).mkdir()
            for key in list(npm_env):
                if key.lower().startswith('npm_config_') or key in ('NPM_TOKEN', 'NODE_AUTH_TOKEN'):
                    npm_env.pop(key)
            for name in ('user.npmrc', 'global.npmrc'):
                (work / name).write_text('')
            npm_env.update(NPM_CONFIG_USERCONFIG=str(work / 'user.npmrc'),
                           NPM_CONFIG_GLOBALCONFIG=str(work / 'global.npmrc'))
            run('install-drizzle', ['npm', 'install', '--ignore-scripts', '--no-audit', '--no-fund',
                                    '--registry=https://registry.npmjs.org'], environment=npm_env)
            shutil.copyfile(work / 'package-lock.json', logs / 'ci-package-lock.json')
            (logs / 'tool-versions.json').write_text(json.dumps(deps, indent=2) + '\n')
            env['LOVABLE_DB_MIGRATION_URL'] = 'postgresql://postgres@127.0.0.1:5432/cw_runner?sslmode=disable'
            migrate = [str(work / 'node_modules/.bin/drizzle-kit'), 'migrate', '--config=drizzle.config.ts']
            # Exercise an actual upgrade from a journal installed BY Drizzle, not forged by the test.
            journal_path.write_text(json.dumps({**journal, 'entries': entries[:-1]}))
            run('drizzle-baseline', migrate)
            ledger_sql = "SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY id),'[]'::jsonb) FROM drizzle.__drizzle_migrations m"
            baseline = json.loads(query('journal-before', ledger_sql))
            if len(baseline) != 11:
                raise AssertionError('Expected eleven historical migrations')
            journal_path.write_text(json.dumps(journal))
            run('drizzle-upgrade', migrate)
            upgraded = json.loads(query('journal-after', ledger_sql))
            if len(upgraded) != 12 or upgraded[:11] != baseline:
                raise AssertionError('Upgrade did not append exactly one journal entry')
            run('drizzle-second', migrate)
            if json.loads(query('journal-second', ledger_sql)) != upgraded:
                raise AssertionError('Second runner invocation changed its journal')
            expect(sqlfile('runner-acl', tests + 'client_privileges_test.sql'), 'CW_ACL_PASS checks=812')
        expect(sqlfile('access', tests + 'client_access_test.sql'), 'CW_ACCESS_PASS')
        clean('fixtures-after-access')
        expect(sqlfile('reapply-after', tests + 'client_privileges_reapply_test.sql'), 'CW_REAPPLY_PASS')
        # Build one transaction from the existing access and reapply tests; only remove transaction wrappers.
        access = (work / tests / 'client_access_test.sql').read_text()
        if not access.rstrip().endswith('ROLLBACK;'):
            raise AssertionError('Access test transaction wrapper changed')
        access = access.rstrip()[:-len('ROLLBACK;')]
        reapply = (work / tests / 'client_privileges_reapply_test.sql').read_text()
        if reapply.count('BEGIN;') != 1:
            raise AssertionError('Reapply test transaction wrapper changed')
        reapply = reapply.replace('BEGIN;', '', 1)
        # Generated file lives alongside originals, preserving psql relative \ir includes.
        populated = work / tests / 'ci_populated.sql'
        populated.write_text(access + '\n' + reapply)
        expect(sqlfile('reapply-populated', tests + 'ci_populated.sql'), 'CW_REAPPLY_PASS')
        clean('fixtures-after-reapply')
        run('corrected-catalog', psql + ['-At', '-f', tests + 'client_privileges_catalog.sql'])
        if mode == 'sql':
            failures = []
            for suite, marker in [('permissions', 'CW_TEST_RESULTS'), ('ingestion', 'CW_INGEST_RESULTS'),
                                  ('c02', 'CW_C02_RESULTS'), ('c03', 'CW_C03_RESULTS')]:
                text = run('historical-' + suite, psql + ['-f', tests + suite + '_test.sql'], allow_error=True)
                # These historical tests intentionally raise to roll back (psql exits 3).
                if results[-1]['exit_code'] != 3 or not re.search(marker + r' pass=\d+ fail=0(?: |$)', text) or re.search(r'not_run=[1-9]', text):
                    failures.append(suite)
                clean('fixtures-after-' + suite)
            if failures:
                raise AssertionError('Historical suites failed/incomplete: ' + ', '.join(failures))
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        (logs / 'failure.txt').write_text(error + '\n')
    finally:
        summary = f'## Permissions / {mode}\n\n' + ('FAILED: ' + error if error else 'PASS: expected assertions completed.') + '\n\n'
        summary += '| Step | Exit |\n|---|---|\n'
        summary += ''.join(f"| {r['step']} | {r['exit_code']} |\n" for r in results)
        summary += '\nHistorical suite exit 3 is intentional only with its fail=0 result marker. SQL tests use synthetic data.\n'
        (logs / 'summary.md').write_text(summary)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
                output.write(summary)
    if error:
        raise SystemExit(error)


if __name__ == '__main__':
    main()
