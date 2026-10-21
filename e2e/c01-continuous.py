"""Mission 20.1: exactly three customers, real local auth and continuous C01 HTTP.

Run from an isolated source copy after start_backend.py --local-mvp.
No operational seeds, analysis RPCs, hosted endpoints, or automatic interventions.
"""
import concurrent.futures
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import time
import uuid
import urllib.request
import urllib.error
from c01_emitter import send

def verify_minute_quota(endpoint, ca, secret):
    # Keep the timed quota probe separate from expensive database assertions.
    # The database clock is real; no timestamp or quota state is altered.
    now = dt.datetime.now(dt.timezone.utc)
    if now.second >= 50:
        time.sleep(61 - now.second)
    minute = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    attempts = []
    for index in range(31):
        operation = str(uuid.uuid4())
        status, result, headers = send(endpoint, secret, {'invalid': True}, operation, ca)
        attempts.append(dict(label='quota probe (no rows)', operation=operation,
            rows=0, http_status=status, inserted=0, duplicates=0,
            batch_id=result.get('batch_id')))
        assert status == (400 if index < 30 else 429), (index, status, result)
        if index == 30:
            assert headers.get('Retry-After') or headers.get('retry-after')
    assert dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0) == minute
    return attempts


assert os.environ.get('CW_LOCAL_MVP') == '1'
assert os.environ.get('PGHOST') == '127.0.0.1'
assert os.environ.get('PGDATABASE') == 'cw_e2e'
info = json.loads(subprocess.check_output(['docker', 'inspect', 'cw-mvp-db']))[0]
assert info['Config']['Image'] == 'postgres:17'
assert info['Config']['Labels']['centerway.disposable'] == 'mvp'
assert all(m['Type'] == 'tmpfs' for m in info['Mounts'])
cfg = json.loads(Path('e2e/private/public.json').read_text())
assert cfg['url'] == 'http://127.0.0.1:54321'
private = Path('e2e/private')
logs = Path('e2e/logs')
newid = lambda: str(uuid.uuid4())

def sql(query):
    r = subprocess.run(['psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1'],
        input=query, text=True, capture_output=True, check=True)
    return r.stdout.strip()

def lit(value):
    return "'" + str(value).replace("'", "''") + "'"

sessions = {}
def rest(path, body=None, role='admin', method='POST'):
    token = sessions.get(role, cfg['anon'])
    req = urllib.request.Request(cfg['url'] + path,
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={'apikey': cfg['anon'], 'Authorization': 'Bearer ' + token,
                 'Content-Type': 'application/json', 'Prefer': 'return=representation'})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or 'null')
    except urllib.error.HTTPError as r:
        return r.code, json.loads(r.read() or 'null')

def rpc(name, body, role='admin'):
    status, result = rest('/rest/v1/rpc/' + name, body, role)
    assert status == 200, (name, status, result)
    return result

assert sql('SELECT count(*) FROM subjects') == '0', 'Use a fresh database; no seeds'
for role in ['admin', 'operator', 'viewer']:
    account = {'email': 'mission20-' + role + '@example.invalid',
               'password': secrets.token_urlsafe(30) + '-Aa1!'}
    assert rest('/auth/v1/signup', account, role)[0] == 200
    status, result = rest('/auth/v1/token?grant_type=password', account, role)
    assert status == 200 and result['user']['email_confirmed_at']
    sessions[role] = result['access_token']
    account['id'] = result['user']['id']
    # Credentials remain private and are never included in the report.
    (private / ('mission20-' + role + '.json')).write_text(json.dumps(account))
    (private / ('mission20-' + role + '.json')).chmod(0o600)
tenant = rpc('create_tenant', {'_name': '[SYNTHETIC] Mission 20.1', '_subject_unit_type': 'organization'})
for role in ['operator', 'viewer']:
    account = json.loads((private / ('mission20-' + role + '.json')).read_text())
    rpc('add_tenant_member', {'_tenant_id': tenant, '_user_id': account['id'], '_role': role})
profile = rpc('create_value_profile_draft', {'_tenant_id': tenant,
    '_promise': '[SYNTHETIC] Continuous external measurements',
    '_expected_outcome': '[SYNTHETIC] Human review only'})
indicator = dict(tenant_id=tenant, profile_id=profile, key='cycle_minutes', name='Cycle duration',
    classification='outcome', value_type='numeric', unit='min', direction='lower_is_better',
    baseline_method='fixed_value', baseline_value=100, baseline_min_period_days=1,
    observation_window_days=1, comparison_window_days=1, min_coverage_pct=100,
    min_denominator=1, target_value=60, deterioration_kind='absolute',
    deterioration_operator='gt', deterioration_value=150, deterioration_consecutive_windows=2,
    recovery_kind='absolute', recovery_operator='lte', recovery_value=60,
    recovery_consecutive_windows=2, aggregation='mean', expected_cadence_days=1,
    denominator_mode='observation_count')
assert rest('/rest/v1/profile_indicators', indicator)[0] == 201
assert rest('/rest/v1/profile_indicators', dict(tenant_id=tenant, profile_id=profile,
    key='workflow_fact', name='Workflow state', classification='context', value_type='text',
    unit='estado', direction='higher_is_better'))[0] == 201
rpc('approve_value_profile', {'_profile_id': profile})
subjects = {}
for i in range(1, 4):
    ref = 'mission20-client-%03d' % i
    status, records = rest('/rest/v1/subjects?select=id', dict(tenant_id=tenant,
        external_ref=ref, display_name='[SYNTHETIC] Client ' + str(i)))
    assert status == 201
    subjects[ref] = records[0]['id']
assert sql('SELECT count(*) FROM subjects') == '3'
source = 'synthetic-mission20'
def credential():
    args = dict(_tenant_id=tenant, _name='[SYNTHETIC] Continuous emitter', _source=source,
        _expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(),
        _operation_id=newid())
    for role in ['operator', 'viewer']:
        assert rest('/rest/v1/rpc/create_ingestion_credential', args, role)[0] == 403
    c = rpc('create_ingestion_credential', args)
    assert rpc('create_ingestion_credential', args)['secret'] is None
    return c
c = credential()
subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
    '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost',
    '-keyout', str(private/'ingestion-key.pem'), '-out', str(private/'ingestion-cert.pem')],
    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
(private/'ingestion-key.pem').chmod(0o600)
ca = str(private/'ingestion-cert.pem')
endpoint = 'https://127.0.0.1:54443/functions/v1/ingest-v1/observations'
midnight = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
def date(days):
    return (midnight+dt.timedelta(days=days)).isoformat().replace('+00:00', 'Z')
def row(ref=None, day=-1, value='50'):
    return dict(subject_external_ref=ref or next(iter(subjects)), indicator_key='cycle_minutes',
        observed_at=date(day), value_numeric=value, unit='min', idempotency_key=newid())
def payload(rows):
    return dict(profile_id=profile, source=source,
        coverage=dict(start=date(-10), end=date(0), declared=True), rows=rows)

# Compare every public table except C01's writable records and trigger-only audit.
tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN "
    "('observations','ingestion_batches','ingestion_credentials','ingestion_api_events','ingestion_api_requests','audit_log') ORDER BY tablename").splitlines()
def snapshot():
    # One statement avoids per-table process overhead and uses one MVCC snapshot.
    queries = ["SELECT " + lit(t) + " AS name, md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),'[]')::text) AS hash FROM public.\"" + t + "\" x" for t in tables]
    return json.loads(sql("SELECT jsonb_object_agg(name,hash) FROM (" + " UNION ALL ".join(queries) + ") snapshots"))

before = snapshot()
ledger = []
expected = {}
checks = []
log = open(logs/'mission20-http.log', 'w')
server = subprocess.Popen(['bun', 'run', 'e2e/ingestion-server.ts'], stdout=log, stderr=subprocess.STDOUT)
def ingest(p, expect=200, operation=None, secret=None, label='measurement', url=None):
    op = operation or newid()
    status, result, headers = send(url or endpoint, secret or c['secret'], p, op, ca)
    ledger.append(dict(label=label, operation=op, rows=len(p.get('rows', [])),
        http_status=status, inserted=result.get('inserted', 0),
        duplicates=result.get('duplicates', 0), batch_id=result.get('batch_id')))
    assert status == expect, (label, status, result)
    assert snapshot() == before, 'An ingestion changed non-C01 public state'
    return result
try:
    for _ in range(100):
        try:
            conn = http.client.HTTPSConnection('127.0.0.1', 54443,
                context=ssl.create_default_context(cafile=ca), timeout=1)
            conn.request('GET', '/functions/v1/ingest-v1/observations')
            assert conn.getresponse().status == 405
            conn.close()
            break
        except OSError:
            time.sleep(.1)
    else:
        raise AssertionError('Local TLS server did not start')
    # Three arrival waves, different observation dates, precision and high values.
    first = None
    for wave, day in enumerate([-3, -2, -1]):
        for i, ref in enumerate(subjects):
            r = row(ref, day, str(200 + 10*i + wave) + '.123456789')
            p = payload([r]); op = newid()
            result = ingest(p, operation=op)
            expected[r['idempotency_key']] = r
            if first is None:
                first = (p, op, result)
        time.sleep(.15)
    for ref in subjects:
        r = row(ref); r.pop('value_numeric'); r.update(indicator_key='workflow_fact',
            value_text='[SYNTHETIC] disabled', unit='estado')
        ingest(payload([r]), label='text'); expected[r['idempotency_key']] = r
    checks.append('3 clients; 3 timed waves; numeric precision; text values')
    p, op, original_result = first
    assert ingest(p, operation=op, label='request replay')['batch_id'] == original_result['batch_id']
    assert ingest(p, label='observation replay')['duplicates'] == 1
    changed = json.loads(json.dumps(p)); changed['rows'][0]['value_numeric'] = '999'
    ingest(changed, 409, operation=op, label='request conflict')
    ingest(changed, 409, label='observation conflict')
    original = sql('SELECT id FROM observations WHERE idempotency_key='+lit(p['rows'][0]['idempotency_key']))
    correction = {**p['rows'][0], 'idempotency_key': newid(), 'value_numeric': '45.987654321',
                  'corrects_observation_id': original}
    ingest(payload([correction]), label='correction'); expected[correction['idempotency_key']] = correction
    fork = {**correction, 'idempotency_key': newid(), 'value_numeric': '44'}
    ingest(payload([fork]), 422, label='correction fork')
    checks.append('request/row replay; immutable correction; conflicts and correction fork')
    # Fresh credential keeps invalid probes independent of the documented quota.
    c = credential()
    bad_rows = [
        ({'subject_external_ref': 'unknown'}, 'unknown client'),
        ({'indicator_key': 'unknown'}, 'unknown indicator'),
        ({'unit': 'hours'}, 'wrong unit'),
        ({'value_numeric': 'NaN'}, 'non-finite number'),
        ({'value_numeric': 'abc'}, 'invalid number'),
        ({'observed_at': '2026-02-30T00:00:00Z'}, 'invalid calendar date'),
        ({'observed_at': date(-11)}, 'outside coverage'),
        ({'observed_at': date(1)}, 'future date'),
        ({'corrects_observation_id': newid()}, 'unknown correction'),
    ]
    for patch, label in bad_rows:
        ingest(payload([{**row(), **patch}]), 422, label=label)
    for patch, label in [({'source': 'forged'}, 'wrong source'),
                          ({'tenant_id': newid()}, 'tenant injection'),
                          ({'profile_id': newid()}, 'unapproved profile')]:
        ingest({**payload([row()]), **patch}, 400, label=label)
    good = row()
    ingest(payload([good, {**row(), 'unit': 'bad'}]), 422, label='atomic batch')
    assert sql('SELECT count(*) FROM observations WHERE idempotency_key='+lit(good['idempotency_key'])) == '0'
    checks.append('invalid identity/source/profile/unit/value/date/correction; atomic batch')
    # Real upstream outage, not a mocked fetch.
    assert json.loads(subprocess.check_output(['docker', 'inspect', 'cw-rest']))[0]['Config']['Labels']['centerway.disposable'] == 'true'
    recovery = row(); recovery_payload = payload([recovery]); recovery_op = newid()
    subprocess.run(['docker', 'stop', 'cw-rest'], check=True, stdout=subprocess.DEVNULL)
    try:
        ingest(recovery_payload, 503, operation=recovery_op, label='upstream outage')
    finally:
        subprocess.run(['docker', 'start', 'cw-rest'], check=True, stdout=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if rest('/rest/v1/subjects?select=id', method='GET')[0] == 200:
                break
        except OSError:
            pass
        time.sleep(.1)
    ingest(recovery_payload, operation=recovery_op, label='outage retry')
    expected[recovery['idempotency_key']] = recovery
    # Connection refused before delivery, then same operation/payload succeeds.
    r = row(); pp = payload([r]); oo = newid()
    ingest(pp, None, operation=oo, label='connection refused',
        url='https://127.0.0.1:54444/functions/v1/ingest-v1/observations')
    ingest(pp, operation=oo, label='connection retry'); expected[r['idempotency_key']] = r
    # Send over real TLS, await DB commit without reading any HTTP response, then drop connection.
    r = row(); pp = payload([r]); oo = newid()
    conn = http.client.HTTPSConnection('127.0.0.1', 54443,
        context=ssl.create_default_context(cafile=ca), timeout=10)
    conn.request('POST', '/functions/v1/ingest-v1/observations', json.dumps(pp),
        {'Authorization': 'Bearer '+c['secret'], 'Content-Type': 'application/json', 'Idempotency-Key': oo})
    for _ in range(100):
        if sql('SELECT count(*) FROM observations WHERE idempotency_key='+lit(r['idempotency_key'])) == '1':
            break
        time.sleep(.05)
    else:
        raise AssertionError('Unacknowledged request did not commit')
    conn.close()
    ledger.append(dict(label='response lost after commit', operation=oo, rows=1,
        http_status=None, inserted=1, duplicates=0, batch_id=None))
    ingest(pp, operation=oo, label='lost-response replay'); expected[r['idempotency_key']] = r
    checks.append('real upstream outage; refused connection; response lost after commit; same-ID recovery')
    c = credential()
    r = row(); pp = payload([r]); oo = newid()
    # Independent sender instances concurrently repeat one request.
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: send(endpoint, c['secret'], pp, oo, ca), range(4)))
    assert all(status == 200 for status, _, _ in results)
    assert len({result['batch_id'] for _, result, _ in results}) == 1
    for status, result, _ in results:
        ledger.append(dict(label='concurrent replay', operation=oo, rows=1,
            http_status=status, inserted=result['inserted'], duplicates=result['duplicates'], batch_id=result['batch_id']))
    expected[r['idempotency_key']] = r
    checks.append('4 concurrent requests create one observation and one batch')
    assert rest('/rest/v1/observations', {'tenant_id': tenant})[0] == 403
    assert rest('/rest/v1/ingestion_credentials', {'tenant_id': tenant})[0] == 403
    # Check exact stored identity, value, timestamps, origin, profile and declared periods.
    records = json.loads(sql("SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT o.*, b.coverage_start, b.coverage_end, b.profile_id AS batch_profile FROM observations o JOIN ingestion_batches b ON b.id=o.batch_id) x"))
    assert len(records) == len(expected) == 17
    for record in records:
        r = expected[record['idempotency_key']]
        assert record['tenant_id'] == tenant and record['subject_id'] == subjects[r['subject_external_ref']]
        assert record['source'] == source and record['unit'] == r['unit']
        assert record['indicator_key'] == r['indicator_key'] and record['batch_profile'] == profile
        assert dt.datetime.fromisoformat(record['observed_at']) == dt.datetime.fromisoformat(r['observed_at'].replace('Z', '+00:00'))
        for field, day in [('coverage_start', -10), ('coverage_end', 0)]:
            assert dt.datetime.fromisoformat(record[field]) == dt.datetime.fromisoformat(date(day).replace('Z', '+00:00'))
        assert record['created_by'] is None and record['integration_credential_id']
        if 'value_numeric' in r:
            assert sql('SELECT value_numeric::text FROM observations WHERE id='+lit(record['id'])) == r['value_numeric']
        else:
            assert record['value_text'] == r['value_text']
        assert record['corrects_observation_id'] == r.get('corrects_observation_id')
    # Persisted originals and corrections, plus audit actor provenance.
    assert sql('SELECT value_numeric::text FROM observations WHERE id='+lit(original)) == p['rows'][0]['value_numeric']
    assert sql("SELECT count(*) FROM audit_log WHERE entity_type='observations' AND details->>'actor_kind'='integration' AND actor_id IS NULL") == '17'
    assert snapshot() == before
    assert sql('SELECT count(*) FROM subjects') == '3'
    checks.append('17 exact persisted rows; immutable originals; integration audit provenance; all non-C01 tables unchanged')
    # Credential lifecycle and minute quota use actual database clock and auth.
    expiry = rpc('create_ingestion_credential', dict(_tenant_id=tenant, _name='[SYNTHETIC] Expiry',
        _source=source, _expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=1)).isoformat(), _operation_id=newid()))
    time.sleep(1.1)
    ingest(payload([row()]), 401, secret=expiry['secret'], label='expired credential')
    status, _ = rest('/rest/v1/rpc/revoke_ingestion_credential', {'_tenant_id': tenant, '_credential_id': c['id']})
    assert status == 204
    ingest(payload([row()]), 401, label='revoked credential')
    c = credential()
    quota_ledger = verify_minute_quota(endpoint, ca, c['secret'])
    ledger.extend(quota_ledger)
    assert snapshot() == before
    checks.append('real expiry/revocation; admin-only credentials; direct writes denied; 30/minute quota')
    accepted_rows = sum(x['rows'] for x in ledger
        if x['http_status'] == 200 or x['label'] == 'response lost after commit')
    rejected_rows = sum(x['rows'] for x in ledger
        if x['http_status'] in (400, 401, 409, 413, 422, 429))
    failed_rows = sum(x['rows'] for x in ledger
        if x['http_status'] == 503 or
        (x['http_status'] is None and x['label'] != 'response lost after commit'))
    assert (accepted_rows, rejected_rows, failed_rows) == (23, 19, 2)
    assert sql('SELECT count(*) FROM observations') == '17'
    assert len(ledger) == 74 and sum(x['rows'] for x in ledger) == 44
    report = dict(mission='20.1', customers=3, persisted_observations=17,
        http_attempts=len(ledger), attempted_rows=sum(x['rows'] for x in ledger),
        accepted_measurement_row_attempts=accepted_rows,
        rejected_measurement_row_attempts=rejected_rows,
        transport_failure_measurement_attempts=failed_rows,
        idempotent_measurement_replays=accepted_rows-len(expected),
        response_lost_after_commit=1, empty_envelope_quota_probes=len(quota_ledger),
        customer_observation_counts={ref: int(sql('SELECT count(*) FROM observations WHERE subject_id='+lit(subject)))
            for ref, subject in subjects.items()},
        response_status_counts={str(s): sum(x['http_status'] == s for x in ledger)
            for s in sorted({x['http_status'] for x in ledger}, key=str)},
        checks=checks, requests=ledger, unchanged_tables=tables,
        hosted_access=False, automatic_core_changes=False)
    (logs/'mission20-results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k not in ('requests', 'unchanged_tables')}, indent=2))
finally:
    (logs/'mission20-attempts.json').write_text(json.dumps(ledger, indent=2))
    server.terminate(); server.wait(timeout=10); log.close()
