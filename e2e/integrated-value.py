"""Integrated value engineering: ten SaaS customers through C01 -> C02 -> C03 -> C04.

Requires a fresh labelled tmpfs stack from start_backend.py --local-mvp.
Expected values live in integrated-value-plan.json, fixed before any measurements.
"""
import datetime as dt
import concurrent.futures
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
plan = json.loads(Path('e2e/integrated-value-plan.json').read_text())
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

assert sql('SELECT count(*) FROM subjects') == '0', 'Fresh disposable database required'
for role in ['admin','operator','viewer','outsider']:
    account = dict(email='integrated-value-'+role+'@example.invalid',password=secrets.token_urlsafe(30)+'-Aa1!')
    assert rest('/auth/v1/signup',account,role)[0] == 200
    status, result = rest('/auth/v1/token?grant_type=password',account,role)
    assert status == 200 and result['user']['email_confirmed_at']
    account['id'] = result['user']['id']; accounts[role] = account; sessions[role] = result['access_token']
p = private/'integrated-value-accounts.json'; p.write_text(json.dumps(accounts)); p.chmod(0o600)
tenant = rpc('create_tenant',dict(_name=plan['company'],_subject_unit_type='organization'))
foreign = rpc('create_tenant',dict(_name='[SYNTHETIC] RLS control company',_subject_unit_type='organization'),'outsider')
for role in ['operator','viewer']:
    rpc('add_tenant_member',dict(_tenant_id=tenant,_user_id=accounts[role]['id'],_role=role))
profile = rpc('create_value_profile_draft',dict(_tenant_id=tenant,
    _promise=plan['documents']['promise']['text'],_expected_outcome='Individually documented goals; no global promise conclusion'))
for indicator in plan['indicators']:
    assert rest('/rest/v1/profile_indicators',{**indicator,'tenant_id':tenant,'profile_id':profile})[0] == 201
rpc('approve_value_profile',{'_profile_id':profile})
clients = {c['id']:c for c in plan['clients']}
subjects = {}
for cid, case in clients.items():
    status, records = rest('/rest/v1/subjects?select=id',dict(tenant_id=tenant,
        external_ref='reportpilot-'+cid,display_name='[SYNTHETIC] SaaS customer '+cid))
    assert status == 201; subjects[cid] = records[0]['id']
credential = rpc('create_ingestion_credential',dict(_tenant_id=tenant,_name='[SYNTHETIC] ReportPilot data emitter',
    _source=plan['source'],_expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(),_operation_id=newid()))

allowed = ['observations','ingestion_batches','ingestion_credentials','ingestion_api_requests','ingestion_api_events',
    'c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c03_attempts','c04_configurations','c04_evaluations',
    'audit_log','tenant_value_profiles','profile_indicators']
tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ("+
    ','.join(lit(t) for t in allowed)+') ORDER BY tablename').splitlines()
def snapshot(selected):
    parts = ["SELECT "+lit(t)+" name, md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),'[]')::text) hash FROM public.\""+t+'" x' for t in selected]
    return json.loads(sql('SELECT jsonb_object_agg(name,hash) FROM ('+' UNION ALL '.join(parts)+') x'))
untouched = snapshot(tables)
def unchanged(): check('C05-C10 and unrelated public tables unchanged',snapshot(tables) == untouched)
upstream = ['observations','ingestion_batches','c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs']
latest = {}; configuration_operations = []; baseline_configs = {}; baseline = {}; technical = {}; evaluation_records = []


def definition(cid,key='cycle_minutes'):
    case = clients[cid]; ind = next(i for i in plan['indicators'] if i['key'] == key)
    goal = case if key == 'cycle_minutes' else case['independent']
    capacity = plan['documents']['plans'][case.get('plan','pro')]
    d = dict(promise=plan['documents']['promise']['text'],promise_ref=plan['documents']['promise']['ref'],
        plan_capability=capacity['text'],plan_ref=capacity['ref'],
        customer_goal='[SYNTHETIC] Customer '+cid+': '+key+(' <= ' if key == 'cycle_minutes' else ' >= ')+str(goal['target'])+' in each of two current windows',
        customer_ref='fixture://reportpilot/clients/'+cid+'/goal-'+key+'-v1',
        compatibility='compatible',compatibility_ref='fixture://reportpilot/reviews/'+cid+'/'+key+'/v1',
        unit=ind['unit'],source=plan['source'],aggregation='mean',comparator='lte' if key == 'cycle_minutes' else 'gte',
        target=goal['target'],deadline=date(0),window_count=2,observation_start=date(-4))
    if key == 'cycle_minutes': d.update(case.get('definition_patch',{}))
    return d


def save(cid,key,d,profile_id=None,parallel=False):
    args = dict(_tenant_id=tenant,_subject_id=subjects[cid],_profile_id=profile_id or profile,
        _indicator_key=key,_previous_id=latest.get((cid,key)),_operation_id=newid(),_definition=d)
    old = snapshot(upstream+['c04_evaluations'])
    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _:rpc('save_c04_configuration',args),range(4)))
        check('four concurrent configuration submissions create exactly one version',len(set(ids)) == 1)
        config_id = ids[0]
    else: config_id = rpc('save_c04_configuration',args)
    check('configuration save is idempotent',rpc('save_c04_configuration',args) == config_id)
    check('configuration save cannot evaluate or mutate C01-C03',snapshot(upstream+['c04_evaluations']) == old)
    cfg = read('c04_configurations','id=eq.'+config_id)[0]
    check('configuration stores the exact documented human goal and profile',cfg['definition'] == d
        and cfg['subject_id'] == subjects[cid] and cfg['profile_id'] == args['_profile_id']
        and cfg['created_by'] == accounts['admin']['id'])
    latest[cid,key] = config_id; configuration_operations.append(args); unchanged()
    return cfg

for cid,case in clients.items():
    cfg = save(cid,'cycle_minutes',definition(cid),parallel=cid == '01')
    baseline_configs[cid,'cycle_minutes'] = cfg
    if cid == '06': check('missing goal confirmation is exposed before C03 exists','customer_ref' in cfg['pending_fields'])
    if 'independent' in case:
        baseline_configs[cid,'delivery_pct'] = save(cid,'delivery_pct',definition(cid,'delivery_pct'))

subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost',
    '-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(private/'ingestion-key.pem'),
    '-out',str(private/'ingestion-cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(private/'ingestion-key.pem').chmod(0o600)
ca = str(private/'ingestion-cert.pem'); endpoint = 'https://127.0.0.1:54443/functions/v1/ingest-v1/observations'
log = open(logs/'integrated-value-http.log','w')
server = subprocess.Popen(['bun','run','e2e/ingestion-server.ts'],stdout=log,stderr=subprocess.STDOUT)


def row(cid,key,day,value):
    return dict(subject_external_ref='reportpilot-'+cid,indicator_key=key,observed_at=date(day),value_numeric=str(value),
        unit='min' if key == 'cycle_minutes' else '%',idempotency_key=newid())

def ingest(cid,rows,operation=None,expected_inserted=None):
    old = snapshot(['c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c03_attempts','c04_evaluations'])
    operation = operation or newid()
    payload = dict(profile_id=profile,source=plan['source'],coverage=dict(start=date(-9),end=date(1),declared=True),rows=rows)
    status, result, _ = send(endpoint,credential['secret'],payload,operation,ca)
    requests.append(dict(client=cid,rows=len(rows),operation=operation,http_status=status,result=result))
    assert status == 200 and result['status'] == 'completed' and result['rejected'] == 0,(status,result)
    if expected_inserted is not None: assert result['inserted'] == expected_inserted
    check('C01 never initiates analysis, evidence or goal evaluation',snapshot(['c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c03_attempts','c04_evaluations']) == old)
    unchanged(); return operation,result


def chain(cid,profile_id=None,parallel=False):
    old_evaluations = snapshot(['c04_evaluations'])
    args = dict(_tenant_id=tenant,_subject_id=subjects[cid],_expected_profile_id=profile_id or profile,_as_of=date(0))
    response = rpc('run_deterioration_analysis',args,'operator')
    replay = rpc('run_deterioration_analysis',args,'admin')
    check('C02 same-input replay returns the same immutable run',replay['run_id'] == response['run_id'] and replay['reused'] is True)
    run = read('c02_runs','id=eq.'+response['run_id'])[0]
    results = {r['indicator_key']:r for r in read('c02_results','run_id=eq.'+run['id'])}
    build_args = dict(_tenant_id=tenant,_run_id=run['id'])
    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            builds = list(pool.map(lambda _:rpc('build_evidence_bundle',build_args,'operator'),range(4)))
        check('concurrent C03 calls build once and reuse three times',sum(x['status']=='built' for x in builds)==1
            and sum(x['status']=='reused' for x in builds)==3 and len({x['bundle_id'] for x in builds})==1)
        build = builds[0]
    else: build = rpc('build_evidence_bundle',build_args,'operator')
    bundle = read('c03_bundles','id=eq.'+build['bundle_id'])[0]
    inds = {i['indicator_key']:i for i in read('c03_indicators','bundle_id=eq.'+bundle['id'])}
    refs = read('c03_refs','bundle_id=eq.'+bundle['id'])
    check('C02/C03 never initiate a C04 evaluation',snapshot(['c04_evaluations']) == old_evaluations)
    check('bundle anchors the correct client, profile input, algorithms and cutoff',
        bundle['tenant_id'] == tenant and bundle['subject_id'] == subjects[cid] and bundle['run_id'] == run['id']
        and run['profile_id'] == (profile_id or profile) and run['algorithm_version']=='c02-v2'
        and bundle['algorithm_version']=='c03-v1' and bundle['c02_input_hash']==run['input_hash']
        and instant(bundle['data_cutoff'])==instant(run['data_cutoff']))
    own = read('observations','subject_id=eq.'+subjects[cid])
    by_id = {o['id']:o for o in own}
    for key,result in results.items():
        ind = inds[key]; detail = result['details']
        check('C03 preserves the full C02 indicator snapshot',ind['snapshot'] == dict(c02_status=result['status'],
            c02_reasons=result['reasons'],classification=result['classification'],below_target=result['below_target'],
            baseline_value=result['baseline_value'],details=detail) and ind['c02_result_id']==result['id'])
        available = [o for o in own if o['indicator_key']==key and instant(o['ingested_at'])<=instant(run['data_cutoff'])]
        superseded = {o['corrects_observation_id'] for o in available if o['corrects_observation_id']}
        effective = [o for o in available if o['id'] not in superseded]
        expected_refs = set()
        for window in detail['windows']+[detail['reference']]:
            observations = [o for o in effective if instant(window['start'])<=instant(o['observed_at'])<instant(window['end'])]
            actual_ids = {o['id'] for o in observations}
            covered = len({(instant(o['observed_at'])-instant(window['start'])).days for o in observations})
            mean = float(sum(Decimal(str(o['value_numeric'])) for o in observations)/len(observations)) if observations else None
            check('C02 arithmetic, daily coverage and exact client/window IDs',window['value']==mean
                and window['n']==len(observations) and window['denominator']==len(observations)
                and window['coverage_pct']==50*covered and window['interval']=='[start,end)'
                and set(window['observation_ids'])==actual_ids)
            for oid in actual_ids: expected_refs.add((oid,'numerator',window['label']))
            for correction in window['corrections']:
                for oid in correction['supersedes']: expected_refs.add((oid,'superseded',window['label']))
        actual_refs = [r for r in refs if r['indicator_id']==ind['id']]
        check('C03 has exactly the effective and superseded references',
            {(r['observation_id'],r['role'],r['window_label']) for r in actual_refs}==expected_refs
            and ind['stored_ref_count']==ind['ref_count']==len(actual_refs))
        for ref in actual_refs:
            observation = by_id[ref['observation_id']]
            check('C03 reference copies the exact C01 value, identity, source, hash and correction',
                all(ref[k]==observation[k] for k in ['tenant_id','indicator_key','observed_at','ingested_at','value_numeric',
                    'value_text','unit','source','payload_hash','corrects_observation_id'])
                and ref['source']==plan['source'] and instant(ref['ingested_at'])<=instant(run['data_cutoff']))
    hashes = json.loads(sql(Path('e2e/c03-verify-content.sql').read_text()))
    check('all C03 content hashes independently reconstruct',all(x['valid'] for x in hashes))
    check('C03 does not create an actionable case',bundle['summary']['actionable_case'] is False)
    unchanged(); return dict(run=run,results=results,bundle=bundle,indicators=inds,refs=refs)


def evaluate(cid,key,cfg,data,expected,parallel=False):
    old = snapshot(upstream+['c04_configurations'])
    args = dict(_tenant_id=tenant,_configuration_id=cfg['id'],_bundle_id=data['bundle']['id'])
    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _:rpc('evaluate_c04_configuration',args,'operator'),range(4)))
        check('four concurrent evaluations persist only one result',len(set(ids))==1); eid=ids[0]
    else: eid=rpc('evaluate_c04_configuration',args,'operator')
    check('C04 evaluation replay is idempotent',rpc('evaluate_c04_configuration',args,'operator')==eid)
    e = read('c04_evaluations','id=eq.'+eid)[0]; d=e['details']; cdef=cfg['definition']
    expected_fields=dict(result=expected['c04'],configuration_state=expected['state'],evidence=expected['evidence'],core_disposition=expected['disposition'])
    check('C04 expected result/documentary state/evidence/disposition',all(e[k]==v for k,v in expected_fields.items()))
    check('C04 identity, immutable definition/version and upstream evidence are exact',e['tenant_id']==tenant
        and e['subject_id']==subjects[cid] and e['configuration_id']==cfg['id'] and e['bundle_id']==data['bundle']['id']
        and e['algorithm_version']=='c04-numeric-v1' and e['created_by']==accounts['operator']['id']
        and d['definition']==cdef and d['configuration_version']==cfg['version']
        and d['run_id']==data['run']['id'] and d['profile_id']==data['run']['profile_id']
        and d['bundle_content_hash']==data['bundle']['content_hash']
        and instant(d['data_cutoff'])==instant(data['run']['data_cutoff']) and instant(d['as_of'])==instant(date(0)))
    selected = [w for w in data['results'][key]['details']['windows'] if int(w['label'].split('_')[1])<=cdef['window_count']]
    check('C04 uses exactly the selected C03 windows, never other indicators',d['indicator_key']==key
        and d['windows']==selected and d['comparison_rule']=='each_selected_current_window')
    if e['evidence']=='sufficient':
        numeric_met=all((w['value']<=cdef['target'] if cdef['comparator']=='lte' else w['value']>=cdef['target']) for w in selected)
        check('documented per-window target predicate',d['all_windows_meet_target']==numeric_met)
    check('no causal claim, global promise fulfillment or automatic transition',d['causality']=='not_established'
        and d['promise_fulfillment']=='not_determined' and d['automatic_case_transition'] is False
        and set(d)=={'definition','configuration_version','profile_id','run_id','as_of','data_cutoff','bundle_content_hash',
            'indicator_key','windows','missing_documentation','reasons','all_windows_meet_target','comparison_rule',
            'causality','promise_fulfillment','automatic_case_transition'})
    check('C04 cannot rewrite upstream evidence or configuration history',snapshot(upstream+['c04_configurations'])==old)
    evaluation_records.append(e); unchanged(); return e


def compare_phase(cid,data,expected,key='cycle_minutes'):
    check('predefined C02 temporal classification for '+cid,data['results'][key]['status']==expected['c02'])
    check('predefined C03 eligibility for '+cid,data['indicators'][key]['status']==expected['c03'])


def old_state(data,evaluations):
    return dict(run=read('c02_runs','id=eq.'+data['run']['id'])[0],
        results=read('c02_results','run_id=eq.'+data['run']['id']+'&order=indicator_key'),
        bundle=read('c03_bundles','id=eq.'+data['bundle']['id'])[0],
        indicators=read('c03_indicators','bundle_id=eq.'+data['bundle']['id']+'&order=indicator_key'),
        refs=read('c03_refs','bundle_id=eq.'+data['bundle']['id']+'&order=indicator_id,ordinal'),
        evaluations=[read('c04_evaluations','id=eq.'+e['id'])[0] for e in evaluations])

try:
    for _ in range(100):
        try:
            connection=http.client.HTTPSConnection('127.0.0.1',54443,context=ssl.create_default_context(cafile=ca),timeout=1)
            connection.request('GET','/functions/v1/ingest-v1/observations'); ready=connection.getresponse().status;connection.close()
            if ready==405: break
        except OSError: pass
        time.sleep(.1)
    else: raise AssertionError('HTTPS handler not ready')
    initial_rows = {}; first_operation = None; first_result = None
    for cid,case in clients.items():
        rows=[]
        for label,values in [('cycle_minutes',case['values'])]+([('delivery_pct',case['independent']['values'])] if 'independent' in case else []):
            for day,value in zip([-6,-5,-4,-3,-2,-1],[values[0],values[0],values[1],values[1],values[2],values[2]],strict=True):
                if day!=case.get('missing_day'): rows.append(row(cid,label,day,value))
        initial_rows[cid]=rows; operation,response=ingest(cid,rows,expected_inserted=len(rows))
        if cid=='01': first_operation,first_result=operation,response
    check('64 initial rows persisted for exactly ten synthetic SaaS customers',len(read('observations'))==64 and len(read('subjects'))==10)
    check('API provenance has integration identity, never a forged human actor',all(o['created_by'] is None
        and o['integration_credential_id']==credential['id'] for o in read('observations')))
    _,replay=ingest('01',initial_rows['01'],operation=first_operation)
    check('same C01 request returns its original batch',replay['batch_id']==first_result['batch_id'] and len(read('observations'))==64)
    _,duplicates=ingest('01',initial_rows['01'],expected_inserted=0)
    check('new request with stable observation keys creates no duplicates',duplicates['duplicates']==6 and len(read('observations'))==64)
    summaries={}; preserved={}; baseline_evaluations={}
    for cid,case in clients.items():
        data=chain(cid,parallel=cid=='01'); compare_phase(cid,data,case)
        e=evaluate(cid,'cycle_minutes',baseline_configs[cid,'cycle_minutes'],data,case,parallel=cid=='01')
        entries=[e]; baseline[cid]=data; baseline_evaluations[cid]=entries
        if 'independent' in case:
            other=case['independent'];compare_phase(cid,data,other,'delivery_pct')
            entries.append(evaluate(cid,'delivery_pct',baseline_configs[cid,'delivery_pct'],data,other))
            check('independent outcomes coexist without aggregation or blocking',entries[0]['result']=='achieved' and entries[1]['result']=='not_achieved')
        preserved[cid]=old_state(data,entries)
        summaries[cid]=dict(scenario=case['scenario'],expected={k:case[k] for k in ['c02','c03','c04','state','evidence','disposition']},
            obtained=dict(c02=data['results']['cycle_minutes']['status'],c03=data['indicators']['cycle_minutes']['status'],
                c04=e['result'],state=e['configuration_state'],evidence=e['evidence'],disposition=e['core_disposition']),
            current_values=[w['value'] for w in data['results']['cycle_minutes']['details']['windows']],
            current_coverage=[w['coverage_pct'] for w in data['results']['cycle_minutes']['details']['windows']],
            configuration_version=e['details']['configuration_version'],run=data['run']['id'],bundle=data['bundle']['id'],evaluation=e['id'])
        if cid=='02':
            descriptive=(100-Decimal(str(data['results']['cycle_minutes']['details']['windows'][0]['value'])))/100*100
            check('30 percent improvement does not imply individual goal fulfillment',descriptive==30 and e['result']=='not_achieved')
            summaries[cid]['descriptive_improvement_pct']=float(descriptive)
        if cid=='06': check('missing confirmation stays inconclusive','customer_ref' in e['details']['missing_documentation'] and 'missing_customer_ref' in e['details']['reasons'])
        if cid=='07': check('documentary contradiction is separate from numerical achievement',e['result']=='achieved'
            and e['configuration_state']=='contradiction' and e['core_disposition']=='configuration_review')
        if cid=='10': summaries[cid]['independent']=dict(expected=case['independent'],obtained=dict(c02=data['results']['delivery_pct']['status'],c03=data['indicators']['delivery_pct']['status'],c04=entries[1]['result']))
    for cid in ['08','09']:
        follow=clients[cid]['followup'];addition=row(cid,'cycle_minutes',follow['day'],follow['value'])
        if follow['kind']=='correction':
            original=next(o for o in read('observations','subject_id=eq.'+subjects[cid]) if instant(o['observed_at'])==instant(date(-1)))
            addition['corrects_observation_id']=original['id']
        ingest(cid,[addition],expected_inserted=1)
        added=read('observations','idempotency_key=eq.'+addition['idempotency_key'])[0]
        check('new information arrives after the original cutoff without backdating',instant(added['ingested_at'])>instant(baseline[cid]['run']['data_cutoff']))
        data=chain(cid);compare_phase(cid,data,follow)
        e=evaluate(cid,'cycle_minutes',baseline_configs[cid,'cycle_minutes'],data,follow)
        check('new C02 and C03 histories correctly link their prior versions',data['run']['revision_of']==baseline[cid]['run']['id']
            and data['bundle']['revision_of']==baseline[cid]['bundle']['id'])
        if cid=='09': check('correction preserves the original as superseded evidence',any(r['observation_id']==original['id']
            and r['role']=='superseded' and r['superseded_by']==added['id'] for r in data['refs']))
        summaries[cid]['followup']=dict(expected=follow,obtained=dict(c02=data['results']['cycle_minutes']['status'],
            c03=data['indicators']['cycle_minutes']['status'],c04=e['result']),evaluation=e['id'],old_evaluation_preserved=True)
        technical[cid+'-followup']=data
    probe_results=[]
    for probe in plan['probes']:
        cid=probe['client'];d=definition(cid);patch=probe['patch'].copy()
        if 'deadline_day' in patch: patch['deadline']=date(patch.pop('deadline_day'))
        d.update(patch);cfg=save(cid,'cycle_minutes',d)
        e=evaluate(cid,'cycle_minutes',cfg,baseline[cid],probe)
        probe_results.append(dict(name=probe['name'],expected=probe['c04'],obtained=e['result'],state=e['configuration_state'],reasons=e['details']['reasons']))
    # Genuine approved profile supersession; evaluate v2 explicitly, preserve all v1 results.
    old_profile=profile;old_indicators=read('profile_indicators','profile_id=eq.'+old_profile+'&order=key')
    profile_v2=rpc('create_value_profile_version',{'_from_profile_id':old_profile})
    assert rest('/rest/v1/profile_indicators?profile_id=eq.'+profile_v2+'&key=eq.cycle_minutes',{'deterioration_value':155},method='PATCH')[0]==200
    rpc('approve_value_profile',{'_profile_id':profile_v2})
    check('old profile indicator definitions stay immutable',read('profile_indicators','profile_id=eq.'+old_profile+'&order=key')==old_indicators)
    version_data=chain('01',profile_v2);version_cfg=save('01','cycle_minutes',definition('01'),profile_v2)
    version_eval=evaluate('01','cycle_minutes',version_cfg,version_data,clients['01'])
    check('new evaluation anchors exact v2 measurement/configuration profiles',version_data['run']['profile_version']==2
        and version_data['results']['cycle_minutes']['details']['parameters']['deterioration_value']==155)
    mismatch=dict(c04='inconclusive',state='contradiction',evidence='insufficient',disposition='configuration_review')
    mismatch_eval=evaluate('01','cycle_minutes',baseline_configs['01','cycle_minutes'],version_data,mismatch)
    check('profile mismatch cannot borrow evidence from another version','historical_measurement_configuration_mismatch' in mismatch_eval['details']['reasons'])
    for cid,data in baseline.items():
        check('baseline '+cid+' C02/C03/C04 history is unchanged',old_state(data,baseline_evaluations[cid])==preserved[cid])
    # HTTP security and unsupported-policy checks; preserve contract, never approximate.
    save_args=configuration_operations[0]
    check('same operation with changed goal is rejected',rest('/rest/v1/rpc/save_c04_configuration',
        {**save_args,'_definition':{**save_args['_definition'],'target':999}})[0]==400)
    for invalid in [{'aggregation':'median'},{'window_count':1.5},{'global_promise_fulfilled':True},{'weights':[1,1]}]:
        args={**save_args,'_operation_id':newid(),'_previous_id':latest['01','cycle_minutes'],'_definition':{**definition('01'),**invalid}}
        check('unsupported evaluation policy/rule is rejected',rest('/rest/v1/rpc/save_c04_configuration',args)[0]==400)
    check('stale configuration revision is rejected',rest('/rest/v1/rpc/save_c04_configuration',
        {**save_args,'_operation_id':newid(),'_previous_id':baseline_configs['01','cycle_minutes']['id']})[0]==400)
    check('old configuration operation replays after later versions',rpc('save_c04_configuration',save_args)==baseline_configs['01','cycle_minutes']['id'])
    evaluation_args=dict(_tenant_id=tenant,_configuration_id=baseline_configs['01','cycle_minutes']['id'],_bundle_id=baseline['01']['bundle']['id'])
    check('another customer bundle cannot satisfy the goal',rest('/rest/v1/rpc/evaluate_c04_configuration',
        {**evaluation_args,'_bundle_id':baseline['02']['bundle']['id']})[0]==400)
    for role in ['operator','viewer','outsider','anon']:
        check(role+' cannot save a C04 configuration',rest('/rest/v1/rpc/save_c04_configuration',save_args,role)[0] in [401,403])
    for role in ['viewer','outsider','anon']:
        check(role+' cannot evaluate this company',rest('/rest/v1/rpc/evaluate_c04_configuration',evaluation_args,role)[0] in [401,403])
    for table in ['subjects','observations','c02_runs','c03_bundles','c03_refs','c04_configurations','c04_evaluations']:
        check('foreign-company real user cannot read '+table,read(table,role='outsider')==[])
    for table in ['c04_configurations','c04_evaluations']:
        for method,body in [('POST',{'tenant_id':tenant}),('PATCH',{'tenant_id':tenant}),('DELETE',None)]:
            check('direct '+method+' denied on '+table,rest('/rest/v1/'+table+'?tenant_id=eq.'+tenant,body,method=method)[0]==403)
        check('viewer reads company history under RLS',len(read(table,role='viewer'))>0)
    check('old C04 evaluation reuses its stored as_of even after profile supersession',rpc('evaluate_c04_configuration',evaluation_args,'operator')==baseline_evaluations['01'][0]['id'])
    check('configuration/evaluation audit actors are real JWT subjects',sql("SELECT count(*) FROM audit_log WHERE entity_type='c04_configurations' AND actor_id="+lit(accounts['admin']['id']))=='19'
        and sql("SELECT count(*) FROM audit_log WHERE entity_type='c04_evaluations' AND actor_id="+lit(accounts['operator']['id']))=='22')
    unchanged()
    # Existing and focused SQL/RLS regressions are rollback-only.
    before_sql=snapshot(upstream+['subjects','c04_configurations','c04_evaluations'])
    sql_results=[]
    for name,marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS'),('c03','CW_C03_RESULTS')]:
        process=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+name+'_test.sql'],text=True,capture_output=True)
        output=process.stdout+process.stderr;(logs/('integrated-'+name+'-sql.log')).write_text(output)
        match=re.search(marker+r' pass=\d+ fail=0(?: not_run=0)?',output)
        check(name+' SQL regressions pass',process.returncode==3 and match is not None and re.search(r'not_run=[1-9]',output) is None)
        sql_results.append(match.group(0))
    fixture=dict(tenant=tenant,admin=accounts['admin']['id'],operator=accounts['operator']['id'],viewer=accounts['viewer']['id'],outsider=accounts['outsider']['id'],
        subject=subjects['01'],profile=old_profile,config=baseline_configs['01','cycle_minutes']['id'],bundle=baseline['01']['bundle']['id'],other_bundle=baseline['02']['bundle']['id'])
    process=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1'],input='BEGIN; SELECT set_config(\'cw.integrated_fixture\','+lit(json.dumps(fixture))+',true);\n'+Path('e2e/integrated-c04-rls.sql').read_text()+'\nROLLBACK;',text=True,capture_output=True)
    output=process.stdout+process.stderr;(logs/'integrated-c04-sql.log').write_text(output)
    match=re.search(r'CW_INTEGRATED_C04_RESULTS pass=\d+ fail=0',output)
    check('focused C04 SQL/RLS regressions pass',process.returncode==0 and match is not None);sql_results.append(match.group(0))
    check('SQL regressions leave no changes to customers, measurements or history',snapshot(upstream+['subjects','c04_configurations','c04_evaluations'])==before_sql)
    counts=dict(customers=len(read('subjects')),observations=len(read('observations')),c02_runs=len(read('c02_runs')),
        c03_bundles=len(read('c03_bundles')),c03_refs=len(read('c03_refs')),configurations=len(read('c04_configurations')),evaluations=len(read('c04_evaluations')))
    check('exact final ten-customer versioned record counts',counts==dict(customers=10,observations=66,c02_runs=13,c03_bundles=13,c03_refs=83,configurations=19,evaluations=22))
    check('all 13 persisted C03 hashes verify',len(json.loads(sql(Path('e2e/c03-verify-content.sql').read_text())))==13)
    unchanged()
    report=dict(mission='20.3-integrated',base_main_commit='49354db39939d0f4bf828d7a2acaf5d26a656a1f',executed_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        company=plan['company'],as_of=date(0),plan='e2e/integrated-value-plan.json',clients=summaries,probes=probe_results,
        counts=counts,c01_http_attempts=len(requests),measurement_row_attempts=sum(r['rows'] for r in requests),unique_measurements=66,
        idempotent_measurement_replays=12,measurement_rejections=0,sql_regressions=sql_results,
        assertions_passed=len(checks),checks=checks,unchanged_tables=tables,limitations=plan['limitations'],
        product_defects_found=0,hosted_access=False,automatic_interventions=False,global_promise_fulfillment='not_determined')
    (logs/'integrated-value-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (logs/'integrated-value-evaluations.json').write_text(json.dumps(dict(evaluations=read('c04_evaluations'),configurations=read('c04_configurations'),
        c03_indicators=read('c03_indicators'),c03_refs=read('c03_refs'),observations=read('observations'),
        bundles=read('c03_bundles'),runs=read('c02_runs')),indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['clients','checks','unchanged_tables']},ensure_ascii=False,indent=2))
finally:
    (logs/'integrated-value-c01-requests.json').write_text(json.dumps(requests,indent=2)+'\n')
    server.terminate();server.wait(timeout=10);log.close()
