"""Mission 20.2: documented C01 HTTPS inputs -> authorized, real C02 analysis.

Requires a fresh labelled tmpfs stack from start_backend.py --local-mvp.
Expected values live in c02-ingestion-plan.json, fixed before any measurements.
"""
import datetime as dt
from decimal import Decimal
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from c01_emitter import send

assert os.environ.get('CW_LOCAL_MVP') == '1'
assert os.environ.get('PGHOST') == '127.0.0.1'
assert os.environ.get('PGDATABASE') == 'cw_e2e'
info = json.loads(subprocess.check_output(['docker', 'inspect', 'cw-mvp-db']))[0]
assert info['Config']['Image'] == 'postgres:17'
assert info['Config']['Labels']['centerway.disposable'] == 'mvp'
assert '/var/lib/postgresql/data' in info['HostConfig'].get('Tmpfs', {})
assert all(m['Type'] == 'tmpfs' for m in info['Mounts'])
assert info['HostConfig']['PortBindings']['5432/tcp'] == [{'HostIp': '127.0.0.1', 'HostPort': '5432'}]
config = json.loads(Path('e2e/private/public.json').read_text())
assert config['url'] == 'http://127.0.0.1:54321'
plan = json.loads(Path('e2e/c02-ingestion-plan.json').read_text())
private = Path('e2e/private')
logs = Path('e2e/logs')
checks = []
requests = []
newid = lambda: str(uuid.uuid4())
midnight = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

def date(day, hour=0):
    return (midnight + dt.timedelta(days=day, hours=hour)).isoformat().replace('+00:00', 'Z')

def instant(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))

def check(label, condition):
    assert condition, label
    checks.append(label)

def sql(query):
    return subprocess.run(['psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1'], input=query,
        text=True, capture_output=True, check=True).stdout.strip()

def lit(value):
    return "'" + str(value).replace("'", "''") + "'"

sessions = {}
accounts = {}
def rest(path, body=None, role='admin', method='POST'):
    request = urllib.request.Request(config['url'] + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'apikey': config['anon'], 'Authorization': 'Bearer '+sessions.get(role, config['anon']),
                 'Content-Type': 'application/json', 'Prefer': 'return=representation'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or 'null')
    except urllib.error.HTTPError as response:
        return response.code, json.loads(response.read() or 'null')

def rpc(name, args, role='admin'):
    status, result = rest('/rest/v1/rpc/'+name, args, role)
    assert status == 200, (name, status, result)
    return result

def read(table, query='', role='admin'):
    status, result = rest('/rest/v1/'+table+'?'+query, role=role, method='GET')
    assert status == 200, (table, status)
    return result

assert sql('SELECT count(*) FROM subjects') == '0', 'Fresh database required; do not run operational seeds'
assert sql('SELECT count(*) FROM c02_runs') == '0'
for role in ['admin', 'operator', 'viewer', 'outsider']:
    account = dict(email='mission20-2-'+role+'@example.invalid', password=secrets.token_urlsafe(30)+'-Aa1!')
    assert rest('/auth/v1/signup', account, role)[0] == 200
    status, result = rest('/auth/v1/token?grant_type=password', account, role)
    assert status == 200 and result['user']['email_confirmed_at']
    account['id'] = result['user']['id']
    sessions[role] = result['access_token']
    accounts[role] = account
# Private passwords/JWTs/keys are never written to logs or reports.
p = private/'mission20-2-accounts.json'
p.write_text(json.dumps(accounts)); p.chmod(0o600)
tenant = rpc('create_tenant', dict(_name='[SYNTHETIC] Mission 20.2', _subject_unit_type='organization'))
foreign_tenant = rpc('create_tenant', dict(_name='[SYNTHETIC] Isolation only', _subject_unit_type='organization'), 'outsider')
for role in ['operator', 'viewer']:
    rpc('add_tenant_member', dict(_tenant_id=tenant, _user_id=accounts[role]['id'], _role=role))
profile = rpc('create_value_profile_draft', dict(_tenant_id=tenant,
    _promise='[SYNTHETIC] Measure cycle duration', _expected_outcome='[SYNTHETIC] Human assessment required'))
assert rest('/rest/v1/profile_indicators', {**plan['indicator'], 'tenant_id':tenant, 'profile_id':profile})[0] == 201
rpc('approve_value_profile', {'_profile_id':profile})
subjects = {}
for client in plan['clients']:
    status, result = rest('/rest/v1/subjects?select=id', dict(tenant_id=tenant,
        external_ref='mission20-2-'+client, display_name='[SYNTHETIC] Client '+client))
    assert status == 201
    subjects[client] = result[0]['id']
credential = rpc('create_ingestion_credential', dict(_tenant_id=tenant,
    _name='[SYNTHETIC] C02 experiment', _source=plan['source'],
    _expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(), _operation_id=newid()))
check('real password grants; three customers; one approved numeric indicator',
    len(read('subjects')) == 3 and len(read('profile_indicators')) == 1)

# All public business state outside C01/C02/audit must remain unchanged.
allowed = ['observations','ingestion_batches','ingestion_credentials','ingestion_api_requests',
           'ingestion_api_events','c02_runs','c02_results','audit_log']
tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ("+
    ','.join(lit(t) for t in allowed)+') ORDER BY tablename').splitlines()
def snapshot(selected):
    parts = ["SELECT "+lit(t)+" AS name, md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),'[]')::text) AS hash FROM public.\""+t+'" x' for t in selected]
    return json.loads(sql('SELECT jsonb_object_agg(name,hash) FROM ('+' UNION ALL '.join(parts)+') snapshots'))
untouched = snapshot(tables)
def unchanged():
    check('all non-C01/C02 tables unchanged', snapshot(tables) == untouched)

subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
    '-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost',
    '-keyout',str(private/'ingestion-key.pem'),'-out',str(private/'ingestion-cert.pem')],
    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
(private/'ingestion-key.pem').chmod(0o600)
ca = str(private/'ingestion-cert.pem')
endpoint = 'https://127.0.0.1:54443/functions/v1/ingest-v1/observations'
log = open(logs/'mission20-2-http.log', 'w')
server = subprocess.Popen(['bun','run','e2e/ingestion-server.ts'], stdout=log, stderr=subprocess.STDOUT)


def measurement(client, day, value, hour=0):
    return dict(subject_external_ref='mission20-2-'+client, indicator_key=plan['indicator']['key'],
        observed_at=date(day,hour), value_numeric=str(value), unit=plan['indicator']['unit'], idempotency_key=newid())

def ingest(rows):
    history = snapshot(['c02_runs','c02_results'])
    operation = newid()
    status, result, _ = send(endpoint, credential['secret'], dict(profile_id=profile,
        source=plan['source'], coverage=dict(start=date(-9),end=date(1),declared=True), rows=rows), operation, ca)
    requests.append(dict(operation=operation, rows=len(rows), http_status=status, result=result))
    assert status == 200 and result['inserted'] == len(rows) and result['rejected'] == 0, (status,result)
    check('C01 ingestion never runs C02 automatically', snapshot(['c02_runs','c02_results']) == history)
    unchanged()


def args(client, day=0):
    return dict(_tenant_id=tenant, _subject_id=subjects[client], _expected_profile_id=profile, _as_of=date(day))

def analyse(client, day=0, role='admin'):
    observations = snapshot(['observations','ingestion_batches'])
    result = rpc('run_deterioration_analysis', args(client,day), role)
    run = read('c02_runs', 'id=eq.'+result['run_id'])[0]
    values = read('c02_results', 'run_id=eq.'+result['run_id'])
    assert len(values) == 1
    value = values[0]
    check('analysis preserves C01 inputs', snapshot(['observations','ingestion_batches']) == observations)
    check('C02 run subject/profile/algorithm/actor are server-side',
        run['tenant_id'] == tenant and run['subject_id'] == subjects[client] and run['profile_id'] == profile
        and run['algorithm_version'] == plan['algorithm'] and run['created_by'] in [accounts[r]['id'] for r in ['admin','operator']]
        and instant(run['as_of']) == instant(date(day)))
    check('result identifies the same customer and numeric outcome',
        value['tenant_id'] == tenant and value['subject_id'] == subjects[client]
        and value['indicator_key'] == plan['indicator']['key'] and value['classification'] == 'outcome')
    check('no actionable case or objective-achievement/causal claim in summary',
        set(run['summary']) == {'outcome_candidates','usage_candidates','insufficient','persistent','indicators','actionable_case'}
        and run['summary']['actionable_case'] is False and run['summary']['indicators'] == 1)
    check('result contains measurement evidence, not invented causal or objective conclusions',
        set(value) == {'id','tenant_id','run_id','subject_id','indicator_key','classification','status','below_target',
                       'baseline_value','reasons','observation_ids','details','created_at'}
        and set(value['details']) == {'algorithm','windows','reference','baseline_window','parameters','fingerprint',
            'compatible_profile_ids','denominator_parameters','denominator_fingerprint','denominator_compatible_profile_ids'})
    unchanged()
    return result, run, value


def expected_window(actual, expected, observations):
    check('UTC closed-open window boundaries', actual['interval'] == '[start,end)'
        and instant(actual['start']) == instant(date(expected['start_day']))
        and instant(actual['end']) == instant(date(expected['end_day'])))
    check('window value/count/cadence coverage match predetermined criteria',
        actual['value'] == expected['value'] and actual['n'] == expected['n']
        and actual['denominator'] == expected['n'] and actual['expected_slots'] == 2
        and actual['covered_slots'] == expected['n'] and actual['coverage_pct'] == expected['coverage_pct'])
    check('window source and sufficient-data decision', actual['source'] == plan['source']
        and actual['sufficient'] == (expected['coverage_pct'] == 100))
    if 'meets_rule' in expected:
        check('window threshold predicate', actual['meets_rule'] == expected['meets_rule'])
    expected_ids = {o['id'] for o in observations
        if instant(actual['start']) <= instant(o['observed_at']) < instant(actual['end'])}
    check('exact observation IDs belong only to this customer and window', set(actual['observation_ids']) == expected_ids)

try:
    for _ in range(100):
        try:
            connection = http.client.HTTPSConnection('127.0.0.1',54443,
                context=ssl.create_default_context(cafile=ca), timeout=1)
            connection.request('GET','/functions/v1/ingest-v1/observations')
            status = connection.getresponse().status; connection.close()
            if status == 405:
                break
        except OSError:
            pass
        time.sleep(.1)
    else:
        raise AssertionError('Local TLS handler did not start')
    for client, fixture in plan['clients'].items():
        ingest([measurement(client,day,value) for day,value in fixture['measurements']])
    observations = read('observations')
    check('all 20 baseline measurements persisted with API provenance', len(observations) == 20
        and all(o['created_by'] is None and o['integration_credential_id'] == credential['id'] for o in observations))
    check('no C02 runs before an authorized human operation', read('c02_runs') == [])
    baseline = {}
    baseline_report = {}
    for client, fixture in plan['clients'].items():
        response, run, result = analyse(client, role='operator' if client == 'B' else 'admin')
        baseline[client] = (response,run,result)
        own = [o for o in observations if o['subject_id'] == subjects[client]]
        check('baseline '+client+' expected temporal status and target gap', result['status'] == fixture['expected_status']
            and result['below_target'] == fixture['expected_below_target'])
        check('baseline '+client+' input count, cutoff and revision', run['observation_count'] == len(own)
            and run['revision_of'] is None and response['reused'] is False
            and all(instant(o['ingested_at']) <= instant(run['data_cutoff']) for o in own))
        detail = result['details']
        check('approved parameters are frozen in C02 evidence', all(detail['parameters'][k] == v for k,v in plan['indicator'].items())
            and detail['algorithm'] == 'c02-v2' and detail['baseline_window'] is None and result['baseline_value'] == 100)
        for actual, expected in zip(detail['windows'], fixture['expected_windows_newest_first'], strict=True):
            expected_window(actual, expected, own)
        expected_window(detail['reference'],fixture['expected_reference'],own)
        all_ids = set().union(*(set(w['observation_ids']) for w in detail['windows']+[detail['reference']]))
        check('evidence union excludes other customers and measurements outside analysis', set(result['observation_ids']) == all_ids)
        if client == 'C':
            check('missing cadence is insufficient, never a fabricated zero or confirmed deterioration',
                result['reasons'] == ['current_1:coverage_below_minimum','current_1:denominator_below_minimum']
                and detail['windows'][0]['value'] == 210 and 'meets_rule' not in detail['windows'][0]
                and run['summary']['insufficient'] == 1 and run['summary']['outcome_candidates'] == 0)
        else:
            check('sufficient results contain no causal reason narratives', result['reasons'] == []
                and run['summary']['outcome_candidates'] == (1 if client == 'A' else 0))
        baseline_report[client] = dict(expected=fixture['expected_status'], obtained=result['status'],
            current_values_newest_first=[w['value'] for w in detail['windows']],
            current_coverage_pct=[w['coverage_pct'] for w in detail['windows']],
            reference_value=detail['reference']['value'],below_target=result['below_target'],reasons=result['reasons'])
    saved = snapshot(['c02_runs','c02_results'])
    for client, (response,run,_) in baseline.items():
        replay = rpc('run_deterioration_analysis',args(client),'operator')
        check('same inputs reuse immutable run and cutoff for '+client,
            replay['reused'] is True and replay['run_id'] == run['id'])
    check('replay writes no new runs or results', snapshot(['c02_runs','c02_results']) == saved)
    # One previous anchor demonstrates that one breached window is not persistence.
    _, historical, hresult = analyse('A', plan['historical_A']['as_of_day'])
    check('historical anchor has one breached window, no confirmed deterioration',
        hresult['status'] == plan['historical_A']['expected_status']
        and [w['value'] for w in hresult['details']['windows']] == [160,100]
        and hresult['details']['reference']['value'] == 100 and historical['revision_of'] is None)
    # Late event-time measurement: a new human analysis creates a revision; no old rewrite.
    late = plan['late_A']
    added = measurement('A',late['observed_day'],late['value'],late['observed_hour'])
    ingest([added])
    new_observation = read('observations','idempotency_key=eq.'+added['idempotency_key'])[0]
    old_run = baseline['A'][1]; old_result = baseline['A'][2]
    check('late measurement was not available at original data cutoff',
        instant(new_observation['ingested_at']) > instant(old_run['data_cutoff'])
        and new_observation['id'] not in old_result['observation_ids'])
    _, revision, rresult = analyse('A')
    current = rresult['details']['windows'][0]
    check('late input creates a correctly linked revision with a new input hash',
        revision['revision_of'] == old_run['id'] and revision['input_hash'] != old_run['input_hash']
        and revision['observation_count'] == 10 and instant(revision['data_cutoff']) > instant(old_run['data_cutoff']))
    check('revised mean is 530/3, with three observations but only two covered slots',
        abs(Decimal(str(current['value']))-Decimal(530)/3) < Decimal('0.0000000001')
        and current['n'] == 3 and current['covered_slots'] == 2 and current['coverage_pct'] == 100
        and rresult['status'] == late['expected_status'])
    check('late input is referenced only by the new revision', new_observation['id'] in rresult['observation_ids']
        and read('c02_runs','id=eq.'+old_run['id'])[0] == old_run
        and read('c02_results','run_id=eq.'+old_run['id'])[0] == old_result)
    for client in ['B','C']:
        replay = rpc('run_deterioration_analysis',args(client))
        check('A late data cannot revise '+client, replay['reused'] is True and replay['run_id'] == baseline[client][1]['id'])
    replay = rpc('run_deterioration_analysis',args('A'))
    check('new A revision is reusable', replay['reused'] is True and replay['run_id'] == revision['id'])
    # Real RLS and RPC boundaries; no injected browser sessions or service-role calls.
    for table in ['subjects','observations','c02_runs','c02_results']:
        check('foreign user cannot read '+table, read(table,role='outsider') == [])
    for role in ['viewer','outsider','anon']:
        status, _ = rest('/rest/v1/rpc/run_deterioration_analysis',args('A'),role)
        check(role+' cannot run C02', status in (401,403))
    check('tenant cannot be selected outside real membership',
        rest('/rest/v1/rpc/run_deterioration_analysis',{**args('A'),'_tenant_id':foreign_tenant})[0] == 403)
    check('unknown subject cannot borrow other customer measurements',
        rest('/rest/v1/rpc/run_deterioration_analysis',{**args('A'),'_subject_id':newid()})[0] == 400)
    check('unapproved profile rejected',
        rest('/rest/v1/rpc/run_deterioration_analysis',{**args('A'),'_expected_profile_id':newid()})[0] == 400)
    check('future analysis rejected',
        rest('/rest/v1/rpc/run_deterioration_analysis',{**args('A'),'_as_of':date(1)})[0] == 400)
    for table in ['c02_runs','c02_results']:
        check('direct insert denied on '+table, rest('/rest/v1/'+table,{'tenant_id':tenant})[0] == 403)
        check('direct history update denied on '+table,
            rest('/rest/v1/'+table+'?tenant_id=eq.'+tenant,{'subject_id':subjects['B']},method='PATCH')[0] == 403)
    check('viewer can read the authorized immutable results', len(read('c02_results',role='viewer')) == 5)
    unchanged()
    # Existing SQL regressions always roll back their synthetic fixtures.
    regression_snapshot = snapshot(['c02_runs','c02_results','subjects','observations'])
    regressions = []
    for name, marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS')]:
        process = subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+name+'_test.sql'],text=True,capture_output=True)
        output = process.stdout+process.stderr
        (logs/('mission20-2-regression-'+name+'.log')).write_text(output)
        match = re.search(marker+r' pass=\d+ fail=0(?: not_run=0)?',output)
        check(name+' SQL regression suite', process.returncode == 3 and match is not None
            and re.search(r'not_run=[1-9]',output) is None)
        regressions.append(match.group(0))
    check('SQL regressions leave the three-customer history untouched',
        snapshot(['c02_runs','c02_results','subjects','observations']) == regression_snapshot)
    check('final database contains three customers, 21 C01 rows, five human C02 runs',
        len(read('subjects')) == 3 and len(read('observations')) == 21 and len(read('c02_runs')) == 5)
    unchanged()
    report = dict(mission='20.2',base_main_commit='cfbf4413267d4ce75d9b550133865d3fd3408fab',
        executed_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),as_of=date(0),
        criteria_file='e2e/c02-ingestion-plan.json',customers=3,indicator=plan['indicator'],
        c01_requests=len(requests),c01_measurements_sent=21,c01_measurements_accepted=21,c01_measurements_rejected=0,
        initial_results=baseline_report,historical_A=dict(as_of=date(-2),status=hresult['status']),
        revised_A=dict(status=rresult['status'],current_mean=current['value'],coverage_pct=current['coverage_pct'],
            n=current['n'],revision_of_original=True,old_run_unchanged=True),
        c02_runs=5,assertions_passed=len(checks),checks=checks,sql_regressions=regressions,
        unchanged_tables=tables,automatic_cases=False,invented_causes=False,objective_achievement_declared=False,
        hosted_access=False,product_defects_found=0)
    (logs/'mission20-2-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['indicator','checks','unchanged_tables']},indent=2))
finally:
    (logs/'mission20-2-c01-requests.json').write_text(json.dumps(requests,indent=2)+'\n')
    server.terminate(); server.wait(timeout=10); log.close()
