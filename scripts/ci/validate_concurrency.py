#!/usr/bin/env python3
"""Real two-connection tests; only a disposable GitHub-hosted PostgreSQL service."""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def main():
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and
            os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted',
            'Only run in the disposable GitHub-hosted workflow')
    root = Path(__file__).resolve().parents[2]
    logs = Path(os.environ['RUNNER_TEMP']) / 'cw-concurrency'
    logs.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key in ('PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE', 'PGPASSWORD', 'PGOPTIONS',
                'DATABASE_URL', 'LOVABLE_DB_MIGRATION_URL'):
        env.pop(key, None)
    env.update(PGHOST='127.0.0.1', PGPORT='5432', PGUSER='postgres',
               PGDATABASE='cw_concurrency', PGCONNECT_TIMEOUT='10', PGSSLMODE='disable',
               PGPASSFILE=str(logs / 'no-password-file'))
    psql = ['psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose']
    results = []

    def command(name, args, sql=None):
        proc = subprocess.run(args, input=sql, text=True, cwd=root, env=env,
                              capture_output=True, timeout=50)
        (logs / (name + '.log')).write_text(proc.stdout + proc.stderr)
        require(proc.returncode == 0, f'{name}: exit {proc.returncode}; {proc.stderr[-1200:]}')
        return proc.stdout

    def query(sql):
        return command('last-query', psql + ['-c', sql]).strip()

    def claims(uid):
        token = literal(json.dumps({'sub': uid, 'role': 'authenticated'}))
        return f"SET LOCAL ROLE authenticated; SET LOCAL request.jwt.claims = {token};"

    def result_json(output):
        return json.loads(next(line for line in output.splitlines() if line.startswith('{')))

    def actor(uid, statement):
        return query('BEGIN; ' + claims(uid) + statement + '; COMMIT;')

    def pair(name, uid_a, stmt_a, uid_b, stmt_b, expected_error=None):
        """A completes its operation but holds the transaction. Observe B blocked by A."""
        actor_env = env.copy()
        actor_env['PGAPPNAME'] = 'cw-concurrency-' + name + '-a'
        a = subprocess.Popen(psql, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1,
                             cwd=root, env=actor_env)
        messages = queue.Queue()
        captured = []

        def read_a():
            for line in a.stdout:
                captured.append(line)
                messages.put(line.strip())
            messages.put('__EOF__')

        reader = threading.Thread(target=read_a, daemon=True)
        reader.start()
        b = None
        try:
            a.stdin.write("BEGIN; SET LOCAL statement_timeout='20s'; SELECT pg_backend_pid();\n" +
                          claims(uid_a) + '\n' + stmt_a + ';\n\\echo CW_A_READY\n')
            a.stdin.flush()
            deadline = time.monotonic() + 15
            lines = []
            while time.monotonic() < deadline:
                try:
                    line = messages.get(timeout=max(.01, deadline-time.monotonic()))
                except queue.Empty:
                    break
                require(line != '__EOF__', f'{name}: A exited before operation completed')
                lines.append(line)
                if line == 'CW_A_READY':
                    break
            require(lines and lines[-1] == 'CW_A_READY', f'{name}: A did not reach ready barrier')
            pid_a = int(next(x for x in lines if x.isdigit()))
            b_env = env.copy()
            app_b = 'cw-concurrency-' + name + '-b'
            b_env['PGAPPNAME'] = app_b
            b = subprocess.Popen(psql + ['-c', "BEGIN; SET LOCAL statement_timeout='20s'; " +
                                         claims(uid_b) + stmt_b + '; COMMIT;'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 cwd=root, env=b_env)
            blocked = None
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                data = json.loads(query("SELECT coalesce(jsonb_agg(jsonb_build_object('pid',pid,"
                                        "'blockers',pg_blocking_pids(pid),'wait',wait_event_type)), '[]') "
                                        "FROM pg_stat_activity WHERE application_name=" + literal(app_b)))
                blocked = next((x for x in data if pid_a in x['blockers'] and x['wait'] == 'Lock'), None)
                if blocked:
                    break
                require(b.poll() is None, f'{name}: B completed without overlapping/being blocked')
                time.sleep(.05)
            require(blocked is not None and blocked['pid'] != pid_a,
                    f'{name}: two distinct blocked sessions were not observed')
            a.stdin.write('COMMIT;\n\\q\n')
            a.stdin.flush()
            a.wait(timeout=10)
            reader.join(timeout=2)
            out_b, err_b = b.communicate(timeout=20)
            require(a.returncode == 0, f'{name}: A failed at commit')
            if expected_error:
                # psql -c and -f use different nonzero exit codes; the SQLSTATE is the contract.
                require(b.returncode in (1, 3) and expected_error in err_b,
                        f'{name}: expected SQLSTATE {expected_error}, got {b.returncode}: {err_b}')
            else:
                require(b.returncode == 0, f'{name}: B failed: {err_b}')
            (logs / (name + '.log')).write_text('A:\n' + ''.join(captured) + '\nB:\n' + out_b + err_b)
            item = {'case': name, 'session_a': pid_a, 'session_b': blocked['pid'],
                    'overlap_observed': True, 'expected_error': expected_error}
            return ''.join(captured), out_b, item
        finally:
            for proc in (a, b):
                if proc and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
            if a.stdin:
                a.stdin.close()

    command('create-db', ['createdb', 'cw_concurrency'])
    require(170000 <= int(query('SHOW server_version_num')) < 180000, 'PostgreSQL 17 required')
    command('bootstrap', psql + ['-f', 'supabase/tests/local_privileges_bootstrap.sql'])
    journal = json.loads((root / 'drizzle/migrations/meta/_journal.json').read_text())
    for entry in journal['entries']:
        command(entry['tag'], psql + ['--single-transaction', '-f',
                                    'drizzle/migrations/' + entry['tag'] + '.sql'])

    # Reuse the already-tested setup and role helpers, before any import/run.
    access = (root / 'supabase/tests/client_access_test.sql').read_text()
    marker = "  result := pg_temp.act(operator_a,format($$SELECT public.import_observations"
    require(access.count(marker) == 1, 'Historical setup boundary changed')
    setup = access.split(marker, 1)[0]
    setup += """
  RAISE NOTICE 'CW_FIXTURE %', jsonb_build_object('admin',admin_a,'operator',operator_a,
    'tenant',tenant_a,'profile',profile_a,'subject',subject_a);
END
$test$;
COMMIT;
"""
    command('fixture', psql, setup)
    fixture_log = (logs / 'fixture.log').read_text()
    f = json.loads(re.search(r'CW_FIXTURE (\{[^\n]+\})', fixture_log).group(1))
    tenant, profile, subject = map(literal, (f['tenant'], f['profile'], f['subject']))
    rows = [{'subject_external_ref': 'acl-a', 'indicator_key': 'outcome', 'unit': 'count',
             'value_numeric': str(value), 'observed_at': date, 'idempotency_key': 'cc-' + str(i)}
            for i, (value, date) in enumerate([(80,'2026-08-12T00:00:00Z'),
                                             (52,'2026-08-19T00:00:00Z'),
                                             (48,'2026-08-26T00:00:00Z')])]

    def import_sql(expected_profile, payload):
        return (f"SELECT public.import_observations({tenant},{expected_profile},'concurrency',"
                "'2026-08-01T00:00:00Z','2026-09-02T00:00:00Z',true,'synthetic.csv'," +
                literal(json.dumps(payload)) + '::jsonb)::text')

    call = import_sql(profile, rows)
    a, b, item = pair('c01-same-input', f['operator'], call, f['admin'], call)
    ra, rb = result_json(a), result_json(b)
    require(ra['status'] == rb['status'] == 'completed' and ra['inserted'] == 3 and
            rb['inserted'] == 0 and rb['duplicates'] == 3 and
            query(f'SELECT count(*) FROM public.observations WHERE subject_id={subject}') == '3',
            'Concurrent import duplicated or lost observations')
    results.append(item)

    call = f"SELECT public.run_deterioration_analysis({tenant},{subject},{profile},'2026-09-01T00:00:00Z')::text"
    a, b, item = pair('c02-same-input', f['operator'], call, f['admin'], call)
    ra, rb = result_json(a), result_json(b)
    require(ra['run_id'] == rb['run_id'] and not ra['reused'] and rb['reused'],
            'Concurrent C02 did not reuse the same run')
    require(query(f'SELECT count(*) FROM public.c02_runs WHERE subject_id={subject}') == '1',
            'Concurrent C02 created duplicate runs')
    run = literal(ra['run_id'])
    results.append(item)

    call = f'SELECT public.build_evidence_bundle({tenant},{run})::text'
    a, b, item = pair('c03-same-input', f['operator'], call, f['admin'], call)
    ra, rb = result_json(a), result_json(b)
    require(ra['status'] == 'built' and rb['status'] == 'reused' and ra['bundle_id'] == rb['bundle_id'],
            'Concurrent C03 did not reuse bundle')
    require(query(f'SELECT count(*) FROM public.c03_bundles WHERE run_id={run}') == '1' and
            query(f'SELECT count(*) FROM public.c03_refs WHERE bundle_id={literal(ra["bundle_id"])}') == '3',
            'Concurrent C03 duplicated/miscounted references')
    results.append(item)

    draft = actor(f['operator'], f'SELECT public.create_value_profile_version({profile})')
    draft = literal(draft)
    edit = f"UPDATE public.profile_indicators SET name='Concurrent draft edit' WHERE profile_id={draft} RETURNING name"
    approve = f'SELECT (public.approve_value_profile({draft})).id'
    _, _, item = pair('profile-edit-approval', f['operator'], edit, f['admin'], approve)
    require(query(f"SELECT status||':'||(SELECT name FROM public.profile_indicators WHERE profile_id={draft}) "
                  f'FROM public.tenant_value_profiles WHERE id={draft}') == 'approved:Concurrent draft edit',
            'Approval did not serialize with the preceding edit')
    denied = subprocess.run(psql + ['-c', 'BEGIN; ' + claims(f['operator']) + edit + '; COMMIT;'],
                            env=env, cwd=root, text=True, capture_output=True, timeout=10)
    require(denied.returncode in (1, 3) and '42501' in denied.stderr,
            f'Approved edit: expected SQLSTATE 42501, got exit={denied.returncode}: {denied.stderr}')
    results.append(item)

    draft2 = actor(f['operator'], f'SELECT public.create_value_profile_version({draft})')
    stale_rows = [dict(rows[0], idempotency_key='stale-profile-new-row')]
    approve = f'SELECT (public.approve_value_profile({literal(draft2)})).id'
    stale = import_sql(draft, stale_rows)
    _, _, item = pair('approval-stale-import', f['admin'], approve, f['operator'], stale, '22023')
    require(query("SELECT count(*) FROM public.observations WHERE idempotency_key='stale-profile-new-row'") == '0',
            'Stale preview imported against a changed approved profile')
    results.append(item)
    report = {'passed': len(results), 'failed': 0, 'cases': results,
              'environment': 'Disposable PostgreSQL 17; real backend sessions, synthetic auth claims',
              'limits': 'Not HTTP/JWT/browser validation; fixtures die with the disposable service'}
    (logs / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    summary = '# C01–C03 concurrency\n\nFive two-session cases passed.\n\n'
    summary += '\n'.join('- ' + x['case'] + ': distinct backends and blocking observed; assertions passed' for x in results)
    summary += '\n\nNo connection to Supabase/Lovable. Synthetic fixtures in a disposable service.\n'
    (logs / 'summary.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary)
    print('CW_CONCURRENCY_PASS cases=5 distinct_sessions_and_blocking_verified=true', flush=True)


if __name__ == '__main__':
    main()
