"""Mission 20.3: C03 evidence integrity, isolation, fault recovery and history.

Requires a fresh labelled tmpfs stack from start_backend.py --local-mvp.
Expected values live in c02-ingestion-plan.json, fixed before any measurements.
"""
import datetime as dt
import concurrent.futures
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

assert sql('SELECT count(*) FROM subjects') == '0', 'Use a fresh database without operational seeds'
assert sql('SELECT count(*) FROM c03_bundles') == '0'
for role in ['admin','operator','viewer','outsider']:
    account = dict(email='mission20-3-'+role+'@example.invalid', password=secrets.token_urlsafe(30)+'-Aa1!')
    assert rest('/auth/v1/signup',account,role)[0] == 200
    status, result = rest('/auth/v1/token?grant_type=password',account,role)
    assert status == 200 and result['user']['email_confirmed_at']
    sessions[role] = result['access_token']; account['id'] = result['user']['id']; accounts[role] = account
p = private/'mission20-3-accounts.json'; p.write_text(json.dumps(accounts)); p.chmod(0o600)
tenant = rpc('create_tenant',dict(_name='[SYNTHETIC] Mission 20.3 AB',_subject_unit_type='organization'))
foreign = rpc('create_tenant',dict(_name='[SYNTHETIC] Mission 20.3 C',_subject_unit_type='organization'),'outsider')
for role in ['operator','viewer']:
    rpc('add_tenant_member',dict(_tenant_id=tenant,_user_id=accounts[role]['id'],_role=role))

def owner(client): return 'outsider' if client == 'C' else 'admin'
def company(client): return foreign if client == 'C' else tenant

profiles = {}
for role, tid in [('admin',tenant),('outsider',foreign)]:
    profile = rpc('create_value_profile_draft',dict(_tenant_id=tid,
        _promise='[SYNTHETIC] Traceable cycle measurements',_expected_outcome='Human assessment required'),role)
    assert rest('/rest/v1/profile_indicators',{**plan['indicator'],'tenant_id':tid,'profile_id':profile},role)[0] == 201
    rpc('approve_value_profile',{'_profile_id':profile},role)
    profiles[tid] = profile
subjects = {}
for client in plan['clients']:
    status, records = rest('/rest/v1/subjects?select=id',dict(tenant_id=company(client),
        external_ref='mission20-3-'+client,display_name='[SYNTHETIC] Client '+client),owner(client))
    assert status == 201; subjects[client] = records[0]['id']
credentials = {}
source = 'synthetic-mission20-3'
for role, tid in [('admin',tenant),('outsider',foreign)]:
    credentials[tid] = rpc('create_ingestion_credential',dict(_tenant_id=tid,_name='[SYNTHETIC] C03 experiment',
        _source=source,_expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(),_operation_id=newid()),role)

# Only these fixture profile transitions and C01-C03 records may change.
allowed = ['observations','ingestion_batches','ingestion_credentials','ingestion_api_requests','ingestion_api_events',
    'c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c03_attempts','audit_log',
    'tenant_value_profiles','profile_indicators']
tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ("+
    ','.join(lit(t) for t in allowed)+') ORDER BY tablename').splitlines()
def snapshot(selected):
    parts = ["SELECT "+lit(t)+" AS name, md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),'[]')::text) AS hash FROM public.\""+t+'" x' for t in selected]
    return json.loads(sql('SELECT jsonb_object_agg(name,hash) FROM ('+' UNION ALL '.join(parts)+') snapshots'))
untouched = snapshot(tables)
def unchanged(): check('all C04-C10 and unrelated public tables unchanged',snapshot(tables) == untouched)
evidence_tables = ['c03_bundles','c03_indicators','c03_refs']
inputs = ['observations','ingestion_batches','c02_runs','c02_results']
build_calls = []

subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
    '-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost',
    '-keyout',str(private/'ingestion-key.pem'),'-out',str(private/'ingestion-cert.pem')],
    check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(private/'ingestion-key.pem').chmod(0o600)
ca = str(private/'ingestion-cert.pem')
endpoint = 'https://127.0.0.1:54443/functions/v1/ingest-v1/observations'
log = open(logs/'mission20-3-http.log','w')
server = subprocess.Popen(['bun','run','e2e/ingestion-server.ts'],stdout=log,stderr=subprocess.STDOUT)

def measurement(client,day,value):
    return dict(subject_external_ref='mission20-3-'+client,indicator_key=plan['indicator']['key'],
        observed_at=date(day),value_numeric=str(value),unit='min',idempotency_key=newid())

def ingest(client,rows):
    history = snapshot(['c02_runs','c02_results']+evidence_tables+['c03_attempts'])
    tid = company(client)
    status, result, _ = send(endpoint,credentials[tid]['secret'],dict(profile_id=profiles[tid],source=source,
        coverage=dict(start=date(-9),end=date(1),declared=True),rows=rows),newid(),ca)
    requests.append(dict(client=client,rows=len(rows),http_status=status,result=result))
    assert status == 200 and result['inserted'] == len(rows) and result['rejected'] == 0,(status,result)
    check('C01 never initiates C02 or C03',snapshot(['c02_runs','c02_results']+evidence_tables+['c03_attempts']) == history)
    unchanged()

def analyse(client,as_of=None,role=None):
    role = role or owner(client)
    prior = snapshot(evidence_tables+['c03_attempts'])
    response = rpc('run_deterioration_analysis',dict(_tenant_id=company(client),_subject_id=subjects[client],
        _expected_profile_id=profiles[company(client)],_as_of=as_of or date(0)),role)
    run = read('c02_runs','id=eq.'+response['run_id'],role)[0]
    result = read('c02_results','run_id=eq.'+run['id'],role)[0]
    check('C02 never initiates C03',snapshot(evidence_tables+['c03_attempts']) == prior)
    unchanged()
    return run,result

def build(tid,run_id,role='admin'):
    prior = snapshot(inputs)
    response = rpc('build_evidence_bundle',dict(_tenant_id=tid,_run_id=run_id),role)
    build_calls.append(dict(tenant=tid,run=run_id,role=role,result=response))
    check('C03 preserves all C01 and C02 inputs',snapshot(inputs) == prior)
    unchanged()
    return response

def bundle_state(client,bundle_id):
    role = owner(client)
    return (read('c03_bundles','id=eq.'+bundle_id,role)[0],
        read('c03_indicators','bundle_id=eq.'+bundle_id+'&order=indicator_key',role),
        read('c03_refs','bundle_id=eq.'+bundle_id+'&order=ordinal',role))

def verify_bundle(client,response,run,result,expected_status,expected_refs):
    bundle, indicators, refs = bundle_state(client,response['bundle_id'])
    check('one indicator in a bundle for the exact client and C02 run',len(indicators) == 1
        and bundle['tenant_id'] == company(client) and bundle['subject_id'] == subjects[client] and bundle['run_id'] == run['id'])
    indicator = indicators[0]; detail = result['details']
    check('bundle anchors immutable C02 algorithm/input hash/cutoff and human actor',
        bundle['algorithm_version'] == 'c03-v1' and bundle['c02_algorithm_version'] == 'c02-v2'
        and bundle['c02_input_hash'] == run['input_hash'] and instant(bundle['data_cutoff']) == instant(run['data_cutoff'])
        and bundle['created_by'] in [accounts[r]['id'] for r in (['outsider'] if client == 'C' else ['admin','operator'])])
    profile = read('tenant_value_profiles','id=eq.'+run['profile_id'],owner(client))[0]
    check('evidence parameters identify the historical profile and version',
        detail['parameters']['profile_id'] == run['profile_id'] and profile['version'] == run['profile_version']
        and indicator['snapshot']['details'] == detail)
    check('indicator snapshot is exactly the stored C02 result', indicator['c02_result_id'] == result['id']
        and indicator['indicator_key'] == 'cycle_minutes' and indicator['status'] == expected_status
        and indicator['snapshot'] == dict(c02_status=result['status'],c02_reasons=result['reasons'],
            classification=result['classification'],below_target=result['below_target'],
            baseline_value=result['baseline_value'],details=detail))
    expected_reasons = ['c02_insufficient_data']+result['reasons'] if expected_status == 'insufficient' else []
    check('insufficiency is inherited; complete is not a deterioration/actionability claim',
        indicator['reasons'] == expected_reasons and indicator['ref_budget'] == 5000
        and bundle['summary'] == dict(indicators=1,complete=int(expected_status == 'complete'),
            insufficient=int(expected_status == 'insufficient'),context_facts=0,stored_refs=expected_refs,
            ref_budget=5000,actionable_case=False))
    own = {o['id']:o for o in read('observations','subject_id=eq.'+subjects[client],owner(client))}
    windows = detail['windows']+[detail['reference']]
    expected = {}
    for w in windows:
        for oid in w['observation_ids']:
            expected[(oid,'numerator',w['label'])] = None
        for chain in w['corrections']:
            for index,oid in enumerate(chain['supersedes']):
                expected[(oid,'superseded',w['label'])] = chain['observation_id'] if index == 0 else chain['supersedes'][index-1]
    check('exact reference set and stable ordinals, no fabricated or missing observation',
        len(refs) == len(expected) == expected_refs == indicator['ref_count'] == indicator['stored_ref_count']
        and {(r['observation_id'],r['role'],r['window_label']) for r in refs} == set(expected)
        and [r['ordinal'] for r in refs] == list(range(1,len(refs)+1)))
    for ref in refs:
        observation = own[ref['observation_id']]
        w = next(w for w in windows if w['label'] == ref['window_label'])
        check('reference copies exact measurement identity/value/unit/source/hash/correction',
            all(ref[k] == observation[k] for k in ['tenant_id','indicator_key','observed_at','ingested_at',
                'value_numeric','value_text','unit','source','payload_hash','corrects_observation_id'])
            and observation['subject_id'] == subjects[client] and ref['bundle_id'] == bundle['id']
            and ref['indicator_id'] == indicator['id'] and ref['source'] == source)
        check('reference window and cutoff match historical C02 evidence',
            instant(ref['window_start']) == instant(w['start']) and instant(ref['window_end']) == instant(w['end'])
            and instant(ref['window_start']) <= instant(ref['observed_at']) < instant(ref['window_end'])
            and instant(ref['ingested_at']) <= instant(run['data_cutoff'])
            and ref['superseded_by'] == expected[(ref['observation_id'],ref['role'],ref['window_label'])])
    hashes = json.loads(sql(Path('e2e/c03-verify-content.sql').read_text()))
    check('all content hashes independently reconstructed from materialized evidence',
        all(x['valid'] for x in hashes) and bundle['id'] in [x['id'] for x in hashes])
    return bundle,indicator,refs

try:
    for _ in range(100):
        try:
            connection = http.client.HTTPSConnection('127.0.0.1',54443,context=ssl.create_default_context(cafile=ca),timeout=1)
            connection.request('GET','/functions/v1/ingest-v1/observations')
            status = connection.getresponse().status; connection.close()
            if status == 405: break
        except OSError: pass
        time.sleep(.1)
    else: raise AssertionError('HTTPS handler did not start')
    for client,fixture in plan['clients'].items():
        ingest(client,[measurement(client,day,value) for day,value in fixture['measurements']])
    baseline = {}
    for client,fixture in plan['clients'].items():
        run,result = analyse(client,role='operator' if client == 'B' else None)
        check('reused fixture '+client+' has its predefined C02 classification',result['status'] == fixture['expected_status'])
        baseline[client] = run,result
    # A second stored run is intentionally left unbuilt until after the correction/profile change.
    delayed_asof = (midnight-dt.timedelta(hours=1)).isoformat()
    delayed_run, delayed_result = analyse('A',delayed_asof)
    old_profile = profiles[tenant]
    saved_old_indicator = read('profile_indicators','profile_id=eq.'+old_profile)[0]
    a_response = build(tenant,baseline['A'][0]['id'])
    assert a_response['status'] == 'built'
    a_state = verify_bundle('A',a_response,*baseline['A'],'complete',6)
    replay = build(tenant,baseline['A'][0]['id'],'operator')
    check('idempotent A build reuses exact original evidence',replay['status'] == 'reused'
        and replay['bundle_id'] == a_response['bundle_id'] and bundle_state('A',replay['bundle_id']) == (a_state[0],[a_state[1]],a_state[2]))

    # Disposable DB only: inject an exception on B's SECOND reference; first reference must roll back too.
    fault_run = baseline['B'][0]['id']
    sql("""BEGIN;
CREATE FUNCTION public._mission20_3_fault() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
 IF NEW.ordinal = 2 AND EXISTS(SELECT FROM public.c03_bundles b WHERE b.id=NEW.bundle_id AND b.run_id="""+lit(fault_run)+"""::uuid) THEN
  RAISE EXCEPTION 'mission20_3 private injected fault';
 END IF;
 RETURN NEW;
END $f$;
CREATE TRIGGER mission20_3_fault BEFORE INSERT ON public.c03_refs FOR EACH ROW EXECUTE FUNCTION public._mission20_3_fault();
COMMIT;""")
    before_failure = snapshot(evidence_tables)
    try:
        failed = build(tenant,fault_run,'operator')
    finally:
        sql('DROP TRIGGER mission20_3_fault ON public.c03_refs; DROP FUNCTION public._mission20_3_fault();')
    check('mid-build failure returns safe code and rolls back all partial evidence',
        failed == dict(status='failed',code='internal_error:P0001') and snapshot(evidence_tables) == before_failure
        and 'private injected fault' not in json.dumps(failed))
    attempts = read('c03_attempts','requested_run_id=eq.'+fault_run)
    check('failed attempt persists outside bundle rollback with the real actor',len(attempts) == 1
        and attempts[0]['status'] == 'failed' and attempts[0]['bundle_id'] is None
        and attempts[0]['actor_id'] == accounts['operator']['id'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        concurrent_results = list(pool.map(lambda _:build(tenant,fault_run,'operator'),range(4)))
    check('four concurrent retries create one B bundle; three reuse it',
        [r['status'] for r in concurrent_results].count('built') == 1 and [r['status'] for r in concurrent_results].count('reused') == 3
        and len({r['bundle_id'] for r in concurrent_results}) == 1)
    b_state = verify_bundle('B',concurrent_results[0],*baseline['B'],'complete',6)
    c_response = build(foreign,baseline['C'][0]['id'],'outsider')
    c_state = verify_bundle('C',c_response,*baseline['C'],'insufficient',5)
    c_replay = build(foreign,baseline['C'][0]['id'],'outsider')
    check('insufficient C evidence remains insufficient on replay',c_replay['status'] == 'reused'
        and bundle_state('C',c_replay['bundle_id']) == (c_state[0],[c_state[1]],c_state[2]))

    originals = {o['observed_at']:o for o in read('observations','subject_id=eq.'+subjects['A'])}
    original = next(o for o in originals.values() if instant(o['observed_at']) == instant(date(-1)))
    correction = {**measurement('A',-1,50),'corrects_observation_id':original['id']}
    ingest('A',[correction])
    corrected = read('observations','idempotency_key=eq.'+correction['idempotency_key'])[0]
    revised_run,revised_result = analyse('A',role='operator')
    check('correction creates a new C02 revision, mean 110 and no deterioration',
        revised_run['revision_of'] == baseline['A'][0]['id'] and revised_result['status'] == 'no_deterioration'
        and revised_result['details']['windows'][0]['value'] == 110
        and instant(corrected['ingested_at']) > instant(baseline['A'][0]['data_cutoff']))
    revised_response = build(tenant,revised_run['id'],'operator')
    revised_state = verify_bundle('A',revised_response,revised_run,revised_result,'complete',7)
    check('new bundle links prior evidence and includes original as superseded',
        revised_state[0]['revision_of'] == a_state[0]['id']
        and any(r['observation_id'] == original['id'] and r['role'] == 'superseded'
            and r['superseded_by'] == corrected['id'] for r in revised_state[2]))
    replay = build(tenant,baseline['A'][0]['id'])
    check('old A bundle and every old reference remain intact after correction',replay['status'] == 'reused'
        and bundle_state('A',a_state[0]['id']) == (a_state[0],[a_state[1]],a_state[2]))

    # Public profile version RPC; only the copied draft's threshold changes.
    new_profile = rpc('create_value_profile_version',{'_from_profile_id':old_profile})
    assert rest('/rest/v1/profile_indicators?profile_id=eq.'+new_profile,{'deterioration_value':155},method='PATCH')[0] == 200
    rpc('approve_value_profile',{'_profile_id':new_profile}); profiles[tenant] = new_profile
    check('old indicator definition is immutable across profile supersession',
        read('profile_indicators','profile_id=eq.'+old_profile)[0] == saved_old_indicator
        and read('tenant_value_profiles','id=eq.'+old_profile)[0]['status'] == 'superseded')
    version_run,version_result = analyse('A')
    version_response = build(tenant,version_run['id'])
    version_state = verify_bundle('A',version_response,version_run,version_result,'complete',7)
    check('new profile version has its own evidence and frozen threshold 155',
        version_run['profile_version'] == 2 and version_run['profile_id'] == new_profile
        and version_state[1]['snapshot']['details']['parameters']['deterioration_value'] == 155
        and version_state[0]['revision_of'] is None)
    delayed_response = build(tenant,delayed_run['id'])
    delayed_state = verify_bundle('A',delayed_response,delayed_run,delayed_result,'complete',6)
    check('old unbuilt run reconstructs old values after correction and profile change',
        delayed_state[1]['snapshot']['details']['windows'][0]['value'] == 170
        and delayed_state[1]['snapshot']['details']['parameters']['profile_id'] == old_profile
        and delayed_state[1]['snapshot']['details']['parameters']['deterioration_value'] == 150
        and original['id'] in [r['observation_id'] for r in delayed_state[2]]
        and corrected['id'] not in [r['observation_id'] for r in delayed_state[2]])
    replay = build(tenant,version_run['id'])
    check('versioned evidence is idempotent',replay['status'] == 'reused' and replay['bundle_id'] == version_response['bundle_id'])
    for client,state in [('A',a_state),('B',b_state),('C',c_state)]:
        check('original '+client+' evidence is byte-for-byte unchanged',bundle_state(client,state[0]['id']) == (state[0],[state[1]],state[2]))

    before_isolation = snapshot(evidence_tables)
    for tid,run_id,role in [(tenant,baseline['C'][0]['id'],'admin'),(foreign,baseline['A'][0]['id'],'outsider')]:
        rejected = build(tid,run_id,role)
        check('real foreign-company run is rejected without disclosing evidence',rejected == dict(status='rejected',code='run_not_found'))
    check('cross-company requests cannot change evidence',snapshot(evidence_tables) == before_isolation)
    for table in ['c03_bundles','c03_indicators','c03_refs','c03_attempts']:
        check('RLS hides company C from AB in '+table,read(table,'tenant_id=eq.'+foreign) == [])
        check('RLS hides company AB from C in '+table,read(table,'tenant_id=eq.'+tenant,'outsider') == [])
        for method,body in [('POST',{'tenant_id':tenant}),('PATCH',{'tenant_id':tenant}),('DELETE',None)]:
            check('direct '+method+' denied on '+table,
                rest('/rest/v1/'+table+'?tenant_id=eq.'+tenant,body,method=method)[0] == 403)
    for role in ['viewer','outsider','anon']:
        check(role+' cannot build AB evidence',rest('/rest/v1/rpc/build_evidence_bundle',
            dict(_tenant_id=tenant,_run_id=baseline['A'][0]['id']),role)[0] in [401,403])
    check('viewer reads authorized AB evidence only',len(read('c03_bundles',role='viewer')) == 5)
    check('private budget/build helper is inaccessible to human callers',rest('/rest/v1/rpc/_c03_build',
        dict(_tenant_id=tenant,_run_id=baseline['A'][0]['id'],_budget=1))[0] in [401,403,404])
    check('test fault trigger/function were removed',sql("SELECT count(*) FROM pg_trigger WHERE tgname='mission20_3_fault'") == '0'
        and sql("SELECT to_regprocedure('public._mission20_3_fault()') IS NULL") == 't')
    unchanged()

    # Existing C03 integrity/cutoff/budget/security regressions are entirely rolled back.
    before_sql = snapshot(['subjects','observations','c02_runs','c02_results']+evidence_tables+['c03_attempts'])
    process = subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/c03_test.sql'],text=True,capture_output=True)
    output = process.stdout+process.stderr; (logs/'mission20-3-sql.log').write_text(output)
    match = re.search(r'CW_C03_RESULTS pass=\d+ fail=0(?: not_run=0)?',output)
    check('existing C03 SQL regressions pass',process.returncode == 3 and match is not None
        and re.search(r'not_run=[1-9]',output) is None)
    check('C03 SQL fixture changes always roll back',snapshot(['subjects','observations','c02_runs','c02_results']+evidence_tables+['c03_attempts']) == before_sql)
    counts = json.loads(sql("SELECT jsonb_build_object('customers',(SELECT count(*) FROM subjects),'observations',(SELECT count(*) FROM observations),"
        "'runs',(SELECT count(*) FROM c02_runs),'bundles',(SELECT count(*) FROM c03_bundles),'indicators',(SELECT count(*) FROM c03_indicators),"
        "'refs',(SELECT count(*) FROM c03_refs),'attempts',(SELECT jsonb_object_agg(status,n) FROM (SELECT status,count(*) n FROM c03_attempts GROUP BY status) x))"))
    check('exact final counts, failed/rejected attempts and no duplicate evidence',counts == dict(customers=3,observations=21,
        runs=6,bundles=6,indicators=6,refs=37,attempts=dict(built=6,reused=7,failed=1,rejected=2)))
    unchanged()
    report = dict(mission='20.3',base_main_commit='49354db39939d0f4bf828d7a2acaf5d26a656a1f',
        executed_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),fixture_plan='e2e/c02-ingestion-plan.json',
        companies=2,counts=counts,c01_requests=len(requests),c01_measurements_accepted=21,c01_measurements_rejected=0,
        initial_results={c:dict(c02=baseline[c][1]['status'],expected_c03='insufficient' if c == 'C' else 'complete',
            obtained_c03=(c_state if c == 'C' else a_state if c == 'A' else b_state)[1]['status'],refs=5 if c == 'C' else 6) for c in ['A','B','C']},
        corrected_A=dict(c02=revised_result['status'],current_mean=110,c03='complete',refs=7,old_evidence_unchanged=True),
        historical_profiles=dict(old_version=1,old_threshold=150,new_version=2,new_threshold=155,old_delayed_build='complete'),
        content_hashes_verified=6,concurrency=dict(requests=4,built=1,reused=3),
        injected_failure=dict(code=failed['code'],partial_evidence_rows=0,attempt_persisted=True,retry='built'),
        assertions_passed=len(checks),sql_regressions=match.group(0),checks=checks,unchanged_tables=tables,
        product_defects_found=0,hosted_access=False,automatic_cases=False)
    (logs/'mission20-3-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['checks','unchanged_tables']},indent=2))
finally:
    sql('DROP TRIGGER IF EXISTS mission20_3_fault ON public.c03_refs; DROP FUNCTION IF EXISTS public._mission20_3_fault();')
    (logs/'mission20-3-calls.json').write_text(json.dumps(dict(c01=requests,c03=build_calls),indent=2)+'\n')
    server.terminate(); server.wait(timeout=10); log.close()
