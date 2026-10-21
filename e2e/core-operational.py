"""Mission 20.4: grounded C04 -> Core -> C05-C10, eight independent scenarios.

Requires a fresh labelled tmpfs stack from start_backend.py --local-mvp.
Expected values live in core-operational-plan.json, fixed before any measurements.
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
plan = json.loads(Path('e2e/core-operational-plan.json').read_text())
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
    assert status in (200,204), (name, status, result)
    return result

def read(table, query='', role='admin'):
    status, result = rest('/rest/v1/'+table+'?'+query, role=role, method='GET')
    assert status == 200, (table, status)
    return result

assert sql('SELECT count(*) FROM subjects') == '0', 'Fresh disposable database required'
for role in ['admin','approver','operator','viewer','outsider']:
    account=dict(email='core-20-4-'+role+'@example.invalid',password=secrets.token_urlsafe(30)+'-Aa1!')
    assert rest('/auth/v1/signup',account,role)[0]==200
    status,result=rest('/auth/v1/token?grant_type=password',account,role)
    assert status==200 and result['user']['email_confirmed_at']
    account['id']=result['user']['id'];accounts[role]=account;sessions[role]=result['access_token']
p=private/'core-operational-accounts.json';p.write_text(json.dumps(accounts));p.chmod(0o600)
tenant=rpc('create_tenant',dict(_name=plan['company'],_subject_unit_type='organization'))
foreign=rpc('create_tenant',dict(_name='[SYNTHETIC] Core isolation company',_subject_unit_type='organization'),'outsider')
for role in ['approver','operator','viewer']:
    rpc('add_tenant_member',dict(_tenant_id=tenant,_user_id=accounts[role]['id'],_role='admin' if role=='approver' else role))
profile=rpc('create_value_profile_draft',dict(_tenant_id=tenant,_promise='[SYNTHETIC] Reporting workflow included in plan',_expected_outcome='Explicit individual goals; no global value guarantee'))
indicator=dict(key='cycle_minutes',name='[SYNTHETIC] Reporting cycle duration',classification='outcome',value_type='numeric',unit='min',direction='lower_is_better',baseline_method='fixed_value',baseline_value=100,baseline_min_period_days=1,observation_window_days=1,comparison_window_days=1,min_coverage_pct=100,min_denominator=1,target_value=60,deterioration_kind='absolute',deterioration_operator='gt',deterioration_value=150,deterioration_consecutive_windows=2,recovery_kind='absolute',recovery_operator='lte',recovery_value=60,recovery_consecutive_windows=2,aggregation='mean',expected_cadence_days=1,denominator_mode='observation_count')
assert rest('/rest/v1/profile_indicators',{**indicator,'tenant_id':tenant,'profile_id':profile})[0]==201
rpc('approve_value_profile',{'_profile_id':profile})
scenarios={c['id']:c for c in plan['cases']};subjects={}
for cid in scenarios:
    status,rows=rest('/rest/v1/subjects?select=id',dict(tenant_id=tenant,external_ref='sentinel-'+cid,display_name='[SYNTHETIC] Core scenario '+cid))
    assert status==201;subjects[cid]=rows[0]['id']
credential=rpc('create_ingestion_credential',dict(_tenant_id=tenant,_name='[SYNTHETIC] Core scenario HTTP emitter',_source=plan['source'],_expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(),_operation_id=newid()))
allowed=['observations','ingestion_batches','ingestion_credentials','ingestion_api_requests','ingestion_api_events','c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c03_attempts','c04_configurations','c04_evaluations','cw_operational_cases','cw_operational_events','cw_operational_cycles','audit_log','memberships','cw_notification_jobs']
untouched_tables=sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ("+','.join(lit(t) for t in allowed)+') ORDER BY tablename').splitlines()
def snapshot(tables):
    return json.loads(sql('SELECT jsonb_object_agg(name,hash) FROM ('+' UNION ALL '.join("SELECT "+lit(t)+" name,md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),'[]')::text) hash FROM public.\""+t+'" x' for t in tables)+') x'))
untouched=snapshot(untouched_tables)
def unchanged():check('unrelated tables and pilot remain unchanged',snapshot(untouched_tables)==untouched)
upstream=['observations','c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c04_configurations','c04_evaluations']
operations=[];negative=[];cases={};configurations={};inputs={};baseline_history={}
def definition(cid):
    return dict(promise='[SYNTHETIC] Documented reporting workflow',promise_ref='urn:sentinel:promise:v1',plan_capability='[SYNTHETIC] Human workflow configuration and reporting',plan_ref='urn:sentinel:plan:v1',customer_goal='[SYNTHETIC] Cycle <=60 min in each of two daily current windows',customer_ref='urn:sentinel:customer:'+cid,compatibility='contradiction' if cid=='08' else 'compatible',compatibility_ref='urn:sentinel:human-review:'+cid,unit='min',source=plan['source'],aggregation='mean',comparator='lte',target=60,deadline=date(-30),observation_start=date(-40),window_count=2)
for cid in scenarios:
    args=dict(_tenant_id=tenant,_subject_id=subjects[cid],_profile_id=profile,_indicator_key='cycle_minutes',_previous_id=None,_operation_id=newid(),_definition=definition(cid))
    configurations[cid]=rpc('save_c04_configuration',args)
check('human goals documented before measurements',len(read('c04_configurations'))==8 and read('observations')==[])
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(private/'ingestion-key.pem'),'-out',str(private/'ingestion-cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(private/'ingestion-key.pem').chmod(0o600)
ca=str(private/'ingestion-cert.pem');endpoint='https://127.0.0.1:54443/functions/v1/ingest-v1/observations'
server_log=open(logs/'core-operational-http.log','w')
server=subprocess.Popen(['bun','run','e2e/ingestion-server.ts'],stdout=server_log,stderr=subprocess.STDOUT)
def row(cid,day,value,corrects=None,observed_at=None):
    d=dict(subject_external_ref='sentinel-'+cid,indicator_key='cycle_minutes',observed_at=observed_at or date(day),value_numeric=str(value),unit='min',idempotency_key=newid())
    if corrects:d['corrects_observation_id']=corrects
    return d

def ingest(cid,rows,operation=None,inserted=None):
    before=snapshot(['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])
    status,result,_=send(endpoint,credential['secret'],dict(profile_id=profile,source=plan['source'],coverage=dict(start=date(-40),end=date(1),declared=True),rows=rows),operation or newid(),ca)
    requests.append(dict(client=cid,rows=len(rows),http_status=status,result=result))
    assert status==200 and result['status']=='completed' and result['rejected']==0,(status,result)
    if inserted is not None:check('C01 expected inserted rows',result['inserted']==inserted)
    check('C01 does not change operational cases or execute actions',snapshot(['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])==before)
    unchanged();return result

def chain(cid,as_of):
    args=dict(_tenant_id=tenant,_subject_id=subjects[cid],_expected_profile_id=profile,_as_of=as_of)
    run=rpc('run_deterioration_analysis',args,'operator')
    check('C02 idempotent',rpc('run_deterioration_analysis',args,'operator')['run_id']==run['run_id'])
    b=rpc('build_evidence_bundle',dict(_tenant_id=tenant,_run_id=run['run_id']),'operator')
    check('C03 complete or legitimate insufficiency',b['status'] in ['built','reused'])
    evaluation=rpc('evaluate_c04_configuration',dict(_tenant_id=tenant,_configuration_id=configurations[cid],_bundle_id=b['bundle_id']),'operator')
    e=read('c04_evaluations','id=eq.'+evaluation)[0]
    check('C04 remains individual without causes or automatic actions',e['details']['causality']=='not_established' and e['details']['promise_fulfillment']=='not_determined' and e['details']['automatic_case_transition'] is False)
    return dict(run=run['run_id'],bundle=b['bundle_id'],evaluation=evaluation,result=e['result'],state=e['configuration_state'],evidence=e['evidence'])

def current(cid):return read('cw_operational_cases','id=eq.'+cases[cid])[0]
def history(cid,**kw):return rpc('operational_cycle_history',dict(_tenant_id=tenant,_case_id=cases[cid],**kw))
def args(cid,command,payload,operation=None,version=None):
    return dict(_tenant_id=tenant,_case_id=cases[cid],_expected_version=current(cid)['version'] if version is None else version,_operation_id=operation or newid(),_command=command,_payload=payload)
def command(cid,name,payload,role='operator',parallel=False):
    a=args(cid,name,payload);old=snapshot(upstream)
    if parallel:
        with concurrent.futures.ThreadPoolExecutor(4) as pool:out=list(pool.map(lambda _:rest('/rest/v1/rpc/command_operational_case',a,role),range(4)))
        check('four concurrent '+name+' calls persist one event',all(s==200 and r==out[0][1] for s,r in out));eid=out[0][1]
    else:eid=rpc('command_operational_case',a,role)
    check(name+' replay returns original event',rpc('command_operational_case',a,role)==eid)
    event=read('cw_operational_events','id=eq.'+eid)[0]
    check(name+' binds exact case, client, actor and sequence',event['case_id']==cases[cid] and event['subject_id']==subjects[cid] and event['tenant_id']==tenant and event['created_by']==accounts[role]['id'] and event['sequence']==a['_expected_version']+1)
    if name!='observe':check(name+' cannot mutate C01-C04 history',snapshot(upstream)==old)
    else:check('C09 only adds derived C04 evaluations',snapshot(upstream[:-1])=={k:v for k,v in old.items() if k!='c04_evaluations'})
    check('stored request hash is server-computed SHA256',len(event['request_hash'])==64)
    operations.append(dict(client=cid,args=a,event=eid,role=role));unchanged();return event

def reject(label,name,a,role='operator',status=400,message=None):
    before=snapshot(['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])
    s,r=rest('/rest/v1/rpc/'+name,a,role)
    if role=='anon' and status==403:status=401
    check(label+' '+str((s,r)),s==status and (message is None or r.get('message')==message))
    check(label+' is atomic',snapshot(['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])==before)
    negative.append(dict(test=label,http_status=s,code=r.get('code'),message=r.get('message')));return r

def bad(cid,name,payload,label,message=None,role='operator',status=400):return reject(label,'command_operational_case',args(cid,name,payload),role,status,message)
def finding(cid,status='confirmed',proof=None):
    return dict(status=status,finding='[SYNTHETIC] Human interpretation of a recorded workflow condition; causality is not established.',reference='urn:sentinel:investigation:'+cid,observation_ids=[proof or inputs[cid]['proof']] if status=='confirmed' else [])
def plan_payload(seconds=3):return dict(action='[SYNTHETIC] Human reviews a local workflow setting; no external action is performed by this test.',rationale='[SYNTHETIC] Bounded investigation follow-up',success_conditions='Historical individual goal and documented human criteria',limitations='No causal attribution or external certification',reversal='Human review before restoring the setting',reference='urn:sentinel:plan:v1',observation_seconds=seconds)
def approval(seconds=3600):return dict(valid_until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=seconds)).isoformat(),reason='[SYNTHETIC] Explicit authorization of the current plan',reference='urn:sentinel:authorization:v1')
receipt=dict(receipt='[SYNTHETIC] Human records completion of a test checklist; no remote action was attempted or verified.',reference='urn:sentinel:receipt:v1')
decision=dict(close_requested=True,criteria_met=True,material_contradiction=False,reason='[SYNTHETIC] Administrator reviews the original individual closure criteria; no global value or cause claimed.',reference='urn:sentinel:decision:v1')
continuation=dict(reason='[SYNTHETIC] Administrator explicitly requests another investigation after remain_open.',reference='urn:sentinel:continuation:v1')
def wait_until(value):
    # Poll wall time naturally; never mutate server time, rows, functions, or timing guards.
    remaining=(instant(value)-dt.datetime.now(dt.timezone.utc)).total_seconds()
    assert remaining<10,'Only an explicit short prospective test window can be waited here'
    while dt.datetime.now(dt.timezone.utc)<instant(value):time.sleep(.05)
try:
    for _ in range(100):
        try:
            conn=http.client.HTTPSConnection('127.0.0.1',54443,context=ssl.create_default_context(cafile=ca),timeout=1)
            conn.request('GET','/functions/v1/ingest-v1/observations');ready=conn.getresponse().status;conn.close()
            if ready==405:break
        except OSError:pass
        time.sleep(.1)
    else:raise AssertionError('C01 HTTPS handler not ready')
    for cid,c in scenarios.items():
        rows=[row(cid,day,value) for day,value in zip([-28,-27,-26,-4,-3,-2],[100,95,90]+c['after_values'],strict=True) if day!=c.get('missing_day')]
        op=newid();ingest(cid,rows,op,len(rows))
        if cid=='01':
            ingest(cid,rows,op);ingest(cid,rows,inserted=0)
        initial=chain(cid,date(-25));after=chain(cid,date(-1))
        check('predefined C04 entry '+cid,initial['result']==c['c04'] and initial['state']==c['state'])
        if c['mode']=='synthetic_retrospective_history':check('retrospective later goal expectation '+cid,after['result']==('not_achieved' if cid=='05' else 'achieved'))
        signal=read('c02_results','run_id=eq.'+initial['run']+'&indicator_key=eq.cycle_minutes')[0]
        check('entry does not require a C02 deterioration candidate',signal['status']==('insufficient_data' if cid=='07' else 'no_deterioration'))
        proof=next(o['id'] for o in read('observations','subject_id=eq.'+subjects[cid]) if instant(o['observed_at'])==instant(date(-28)))
        inputs[cid]=dict(initial=initial,after=after,proof=proof)
    check('47 unique initial measurements and no automatic cases',len(read('observations'))==47 and read('cw_operational_cases')==[])
    # Immutable baseline for every pre-existing C01-C04 record, including failed eligibility.
    for table in upstream:
        baseline_history[table]=read(table,'order=id')
    for cid,c in scenarios.items():
        a=dict(_tenant_id=tenant,_evaluation_id=inputs[cid]['initial']['evaluation'],_operation_id=newid(),_definition=plan['opening'])
        if c['mode']=='blocked':
            reject('C04 '+cid+' blocks opening','open_operational_case',a,'admin',400,'evaluation_requires_information');continue
        if cid=='01':
            for role in ['operator','viewer','outsider','anon']:
                reject(role+' cannot open a case','open_operational_case',a,role,403)
            reject('eligibility declaration is mandatory','open_operational_case',{**a,'_definition':{**plan['opening'],'eligible':False}},'admin',400,'explicit_eligibility_required')
            with concurrent.futures.ThreadPoolExecutor(4) as pool:out=list(pool.map(lambda _:rest('/rest/v1/rpc/open_operational_case',a),range(4)))
            check('four concurrent openings create one case',all(s==200 and r==out[0][1] for s,r in out));case=out[0][1]
        else:case=rpc('open_operational_case',a)
        cases[cid]=case
        check('opening replay is idempotent',rpc('open_operational_case',a)==case)
        reject('second operation cannot duplicate case '+cid,'open_operational_case',{**a,'_operation_id':newid()},'admin',400,'evaluation_already_has_case')
        reject('changed opening with same UUID conflicts '+cid,'open_operational_case',{**a,'_definition':{**plan['opening'],'eligibility_reason':'changed'}},'admin',400,'idempotency_conflict')
        check('case pins exact original individual contract',current(cid)['evaluation_id']==a['_evaluation_id'] and current(cid)['configuration_id']==configurations[cid] and current(cid)['state']=='investigation')
    check('six eligible cases and two blocked entries',len(read('cw_operational_cases'))==6)
    original_identity={cid:{k:v for k,v in current(cid).items() if k not in ['state','version']} for cid in cases}
    # Explicit owner-only historical fixture, never disabling a product guard or clock.
    fixture=dict(tenant=tenant,actor=accounts['admin']['id'],executed_at=date(-10),cases=[dict(case=cases[cid],proof=inputs[cid]['proof']) for cid in ['04','05','06']])
    sql("BEGIN; SELECT set_config('cw.core_fixture',"+lit(json.dumps(fixture))+",true);\n"+Path('e2e/core-retrospective-history.sql').read_text()+"\nCOMMIT;")
    retrospective=read('cw_operational_events','command=neq.open&order=case_id,sequence')
    check('exactly twelve explicitly marked retrospective events',len(retrospective)==12 and all(e['details']['fixture']=='synthetic_retrospective_history' for e in retrospective))
    # Prospective C05: insufficient/hypothesis never silently become confirmed.
    command('01','investigate',finding('01','hypothesis'))
    bad('01','plan',plan_payload(),'hypothesis cannot plan','confirmed_impediment_required')
    command('01','investigate',finding('01','insufficient'))
    check('insufficient investigation remains needs_information',current('01')['state']=='needs_information')
    bad('01','investigate',{**finding('01'),'observation_ids':[]},'confirmed investigation needs a measured fact','confirmed_requires_observation')
    bad('01','investigate',finding('01',proof=inputs['02']['proof']),'another client evidence is rejected','invalid_or_superseded_evidence_reference')
    command('01','investigate',finding('01'),parallel=True)
    evidence=history('01')['heads']['investigate']['details']
    observation=read('observations','id=eq.'+inputs['01']['proof'])[0]
    check('C05 snapshot exact and confirmation is explicitly human',evidence['confirmation']=='human_interpretation' and evidence['causality']=='not_established' and evidence['reference_validation']=='syntax_and_internal_ownership_only' and all(evidence['evidence'][0][k]==observation[k] for k in ['id','indicator_key','value_numeric','unit','source','observed_at','payload_hash']))
    for seconds in [0,1.5,31536001]:bad('01','plan',plan_payload(seconds),'invalid explicit observation window '+str(seconds),'invalid_observation_window')
    command('01','plan',plan_payload())
    bad('01','record_execution',receipt,'execution requires human authorization','valid_authorization_required')
    bad('01','approve',approval(),'operator cannot authorize',role='operator',status=403,message='admin_required')
    bad('01','approve',approval(-10),'past authorization deadline rejected','valid_authorization_required',role='admin')
    command('01','approve',approval(),'admin')
    execution=command('01','record_execution',receipt,parallel=True)
    ex=execution['details']
    check('prospective execution uses server wall time and explicit three-second window',ex['execution_type']=='human_record' and ex['value_recovery']=='not_proven' and (instant(ex['wait_until'])-instant(ex['executed_at'])).total_seconds()==3 and abs((instant(ex['executed_at'])-dt.datetime.now(dt.timezone.utc)).total_seconds())<3)
    bad('01','observe',dict(bundle_id=inputs['01']['after']['bundle']),'C08 cannot observe prematurely','observation_window_not_elapsed')
    bad('01','record_execution',receipt,'new UUID cannot execute twice','valid_authorization_required')
    bad('01','record_execution',{**receipt,'executed_at':date(-10)},'caller cannot inject historical execution')
    wait_until(ex['wait_until'])
    comparison=command('01','observe',dict(bundle_id=inputs['01']['after']['bundle']))
    check('historical achieved C04 is not post-execution recovery',comparison['details']['after']['all_windows_meet_target'] is True and comparison['details']['result']=='inconclusive' and comparison['details']['sufficient'] is False and 'post_execution_observation_insufficient' in comparison['details']['reasons'])
    command('01','decide',decision,'admin')
    check('prospective insufficient evidence keeps case open',current('01')['state']=='remain_open')
    before_cycle=read('cw_operational_events','case_id=eq.'+cases['01']+'&order=sequence')
    old_execution=next(o for o in operations if o['event']==execution['id'])
    for role in ['operator','viewer','outsider','anon']:bad('01','start_cycle',continuation,role+' cannot start cycle',role=role,status=403)
    command('01','start_cycle',continuation,'admin',parallel=True)
    check('new cycle has no inherited authorization or execution',set(history('01')['heads'])=={'start_cycle'} and history('01')['current']['number']==2)
    bad('01','record_execution',receipt,'previous cycle authorization cannot authorize new execution','valid_authorization_required')
    bad('01','plan',plan_payload(),'new cycle requires new investigation','confirmed_impediment_required')
    check('old execution receipt replays after cycle advance',rpc('command_operational_case',old_execution['args'],'operator')==execution['id'])
    check('old cycle retained byte-for-byte',history('01',_cycle_id=cases['01'])['events']==before_cycle)
    # Prospective C07: revision, natural expiry and current role revocation.
    command('02','investigate',finding('02'));command('02','plan',plan_payload())
    first_approval=command('02','approve',approval(),'approver')
    command('02','plan',{**plan_payload(),'action':'[SYNTHETIC] Human revision of the test checklist'})
    bad('02','record_execution',receipt,'plan revision invalidates prior authorization','valid_authorization_required')
    short=command('02','approve',approval(2),'approver')
    wait_until(short['details']['valid_until'])
    bad('02','record_execution',receipt,'naturally expired authorization cannot execute','valid_authorization_required')
    command('02','approve',approval(),'approver')
    rpc('set_member_role',dict(_tenant_id=tenant,_user_id=accounts['approver']['id'],_role='operator'))
    bad('02','record_execution',receipt,'revoked current approver role blocks execution','approver_no_longer_authorized',status=403)
    rpc('set_member_role',dict(_tenant_id=tenant,_user_id=accounts['approver']['id'],_role='admin'))
    # Renew explicitly; role restoration alone is not used as the new human decision.
    renewed=command('02','approve',approval(),'admin')
    bad('02','record_execution',{**receipt,'executed_at':date(-10)},'valid authorization cannot accept caller-supplied execution time','invalid_command_payload')
    second_exec=command('02','record_execution',receipt)
    check('execution references current revised plan and renewed approval',second_exec['details']['approval_event_id']==renewed['id'] and second_exec['details']['approval_event_id']!=first_approval['id'])
    # Correction of a C05 proof blocks both preparation and execution, without erasing it.
    command('03','investigate',finding('03'));command('03','plan',plan_payload());command('03','approve',approval(),'admin')
    proof=read('observations','id=eq.'+inputs['03']['proof'])[0]
    correction=ingest('03',[row('03',-28,101,proof['id'])],inserted=1)
    check('original C05 evidence remains stored',read('observations','id=eq.'+proof['id'])[0]==proof)
    bad('03','plan',plan_payload(),'corrected C05 proof prevents new plan','investigation_evidence_changed')
    bad('03','record_execution',receipt,'corrected C05 proof prevents authorized execution','investigation_evidence_changed')
    bad('03','investigate',finding('03'),'superseded C05 observation cannot be reconfirmed','invalid_or_superseded_evidence_reference')
    # Retrospective fixtures: present-day authenticated C09/C10, real grounded later evidence.
    for cid in ['04','05','06']:
        comp=command(cid,'observe',dict(bundle_id=inputs[cid]['after']['bundle']))
        check('retrospective C09 is post-execution and sufficient '+cid,comp['details']['sufficient'] is True and comp['details']['result']==('not_achieved' if cid=='05' else 'achieved') and comp['details']['causality']=='not_established')
    # Human textual criteria and material contradictions still prevent closure despite achieved.
    command('04','decide',{**decision,'material_contradiction':True},'admin')
    check('material contradiction prevents closure',current('04')['state']=='remain_open')
    command('04','observe',dict(bundle_id=inputs['04']['after']['bundle']))
    command('04','decide',{**decision,'criteria_met':False},'admin')
    check('pending specific criteria prevent closure',current('04')['state']=='remain_open')
    command('04','observe',dict(bundle_id=inputs['04']['after']['bundle']))
    closure=command('04','decide',decision,'admin',parallel=True)
    check('legitimate historical closure only after all guards pass',current('04')['state']=='closed_resolved' and closure['details']['reasons']==[])
    bad('04','start_cycle',continuation,'closed case cannot reopen','case_closed',role='admin')
    # Unmet goal remains open; concurrent distinct new-cycle operations serialize via HTTP409.
    command('05','decide',decision,'admin')
    check('unmet historical goal keeps case open',current('05')['state']=='remain_open' and 'objective_not_demonstrated' in history('05')['heads']['decide']['details']['reasons'])
    competing=[args('05','start_cycle',continuation) for _ in range(2)]
    with concurrent.futures.ThreadPoolExecutor(2) as pool:out=list(pool.map(lambda a:rest('/rest/v1/rpc/command_operational_case',a),competing))
    check('distinct concurrent cycle starts produce one success and one version conflict',sorted(s for s,r in out)==[200,409] and history('05')['current']['number']==2)
    conflict=next(r for s,r in out if s==409);check('version conflict is logical PT409 without serialization retry',conflict['code']=='PT409' and conflict['message']=='case_version_conflict')
    bad('05','record_execution',receipt,'retrospective cycle approval is not reused in next cycle','valid_authorization_required')
    # Relevant late correction invalidates a previously achieved C09 snapshot.
    before_late=history('06')['heads']['observe'];old_bundle=read('c03_bundles','id=eq.'+inputs['06']['after']['bundle'])[0]
    original=next(o for o in read('observations','subject_id=eq.'+subjects['06']) if instant(o['observed_at'])==instant(date(-2)))
    ingest('06',[row('06',-2,85,original['id'])],inserted=1)
    command('06','decide',decision,'admin')
    late_decision=history('06')['heads']['decide']
    check('late correction prevents closure of previously sufficient achieved comparison',current('06')['state']=='remain_open' and 'new_relevant_evidence_requires_comparison' in late_decision['details']['reasons'])
    revised=chain('06',date(-1))
    check('corrected evidence yields predetermined not achieved',revised['result']=='not_achieved')
    check('corrected analysis and bundle link previous immutable versions',read('c02_runs','id=eq.'+revised['run'])[0]['revision_of']==inputs['06']['after']['run'] and read('c03_bundles','id=eq.'+revised['bundle'])[0]['revision_of']==old_bundle['id'])
    command('06','observe',dict(bundle_id=revised['bundle']))
    command('06','decide',decision,'admin')
    check('new C09 covers correction but still cannot close an unmet goal',current('06')['state']=='remain_open' and history('06')['heads']['observe']['details']['result']=='not_achieved' and 'objective_not_demonstrated' in history('06')['heads']['decide']['details']['reasons'] and 'new_relevant_evidence_requires_comparison' not in history('06')['heads']['decide']['details']['reasons'])
    check('late correction never rewrites original C09 or bundle',read('cw_operational_events','id=eq.'+before_late['id'])[0]==before_late and read('c03_bundles','id=eq.'+old_bundle['id'])[0]==old_bundle)
    # A fresh contract revision requires human review, never silent migration of this case.
    rpc('save_c04_configuration',dict(_tenant_id=tenant,_subject_id=subjects['06'],_profile_id=profile,_indicator_key='cycle_minutes',_previous_id=configurations['06'],_operation_id=newid(),_definition={**definition('06'),'customer_ref':'urn:sentinel:customer:06:reconfirmed-v2'}))
    bad('06','start_cycle',continuation,'new C04 contract blocks continuation of pinned historical case','configuration_revision_requires_review',role='admin')
    # Post-closure corrections preserve an explicit historical decision; no auto-reopening.
    closed_case=current('04');closed_events=read('cw_operational_events','case_id=eq.'+cases['04']+'&order=sequence')
    closed_observation=next(o for o in read('observations','subject_id=eq.'+subjects['04']) if instant(o['observed_at'])==instant(date(-2)))
    ingest('04',[row('04',-2,46,closed_observation['id'])],inserted=1)
    check('late correction after closure does not rewrite or reopen history',current('04')==closed_case and read('cw_operational_events','case_id=eq.'+cases['04']+'&order=sequence')==closed_events)
    # Permissions, cross-company IDs, stale writes, payload integrity and atomic rejection.
    safe=args('01','investigate',finding('01','hypothesis'))
    for role in ['viewer','outsider','anon']:
        reject(role+' cannot command this company','command_operational_case',safe,role,403)
    reject('foreign tenant cannot address primary case','command_operational_case',{**safe,'_tenant_id':foreign},'outsider',400,'case_not_found')
    reject('stale operation cannot advance case','command_operational_case',{**safe,'_expected_version':0},'operator',409,'case_version_conflict')
    reject('same execution operation with altered receipt conflicts','command_operational_case',{**old_execution['args'],'_payload':{**receipt,'receipt':'changed'}},'operator',400,'idempotency_conflict')
    reject('current authorization is checked before replay for viewer','command_operational_case',old_execution['args'],'viewer',403,'write_role_required')
    bad('02','observe',dict(bundle_id=inputs['01']['after']['bundle']),'another client bundle cannot support comparison')
    for table in ['cw_operational_cases','cw_operational_events','cw_operational_cycles','c04_evaluations','observations']:
        check('outsider cannot read '+table,read(table,role='outsider')==[])
        check('viewer can read company '+table,len(read(table,role='viewer'))>0)
    for table in ['cw_operational_cases','cw_operational_events','cw_operational_cycles']:
        for method,body in [('POST',{}),('PATCH',{'tenant_id':tenant}),('DELETE',None)]:
            check('direct '+method+' denied on '+table,rest('/rest/v1/'+table+'?tenant_id=eq.'+tenant,body,method=method)[0]==403)
    check('foreign company cannot read cycle history',rest('/rest/v1/rpc/operational_cycle_history',dict(_tenant_id=tenant,_case_id=cases['01']),'outsider')[0]==403)
    check('cycle of another client rejected',rest('/rest/v1/rpc/operational_cycle_history',dict(_tenant_id=tenant,_case_id=cases['01'],_cycle_id=cases['02']))[0]==400)
    # History pagination is complete, stable, and read-only; Central is also read-only.
    all_events=read('cw_operational_events','case_id=eq.'+cases['01']+'&sequence=lte.'+str(before_cycle[-1]['sequence'])+'&order=sequence')
    seen=[];cursor=-1
    while True:
        page=history('01',_cycle_id=cases['01'],_after_event=cursor,_limit=2);seen.extend(page['events'])
        if not page['has_more_events']:break
        cursor=page['events'][-1]['sequence']
    check('pagination preserves all prior-cycle immutable events',seen==all_events)
    before_reads=snapshot(upstream+['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])
    for _ in range(2):
        for cid in cases:history(cid)
        queue=rpc('core_followup_queue',dict(_tenant_id=tenant,_limit=100))
    check('Central and history reads do not trigger transitions',snapshot(upstream+['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])==before_reads)
    for cid in cases:
        entry=next(i for i in queue['items'] if i.get('case_id')==cases[cid])
        check('Core queue keeps exact case identity '+cid,entry['subject_id']==subjects[cid])
        if cid in ['01','05']:check('Core ignores previous-cycle approval and observation '+cid,entry['next_action']=='investigate' and entry['basis']['cycle_number']==2 and entry['review_at'] is None and not entry['basis']['authorization_valid'])
    for table,rows in baseline_history.items():
        actual={r['id']:r for r in read(table)}
        check('all historical '+table+' records intact',all(actual[r['id']]==r for r in rows))
    for event in retrospective:check('synthetic historical event remains intact',read('cw_operational_events','id=eq.'+event['id'])[0]==event)
    for cid in cases:check('original case identity and contract unchanged '+cid,{k:v for k,v in current(cid).items() if k not in ['state','version']}==original_identity[cid])
    check('all C03 hashes independently reconstructed',all(r['valid'] for r in json.loads(sql(Path('e2e/c03-verify-content.sql').read_text()))))
    # HTTP-authenticated events have genuine auth.uid actors; owner-only fixtures are excluded.
    for op in operations:
        check('real JWT actor in immutable audit log',sql("SELECT count(*) FROM audit_log WHERE entity_type='cw_operational_events' AND entity_id="+lit(op['event'])+" AND actor_id="+lit(accounts[op['role']]['id']))=='1')
    for e in read('cw_operational_events'):
        if e['command'] in ['investigate','observe','decide']:check('no inferred causal conclusion in operational event',e['details']['causality']=='not_established')
        if e['command']=='record_execution':check('receipt proves no recovery or remote action',e['details']['value_recovery']=='not_proven' and e['details']['execution_type'] in ['human_record','synthetic_retrospective_human_report'])
    # SQL role/claim checks are separate from real HTTP logins and always rolled back.
    before_sql=snapshot(upstream+['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])
    sql_results=[]
    for name,marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS'),('c03','CW_C03_RESULTS')]:
        process=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+name+'_test.sql'],text=True,capture_output=True)
        output=process.stdout+process.stderr;(logs/('core-'+name+'-sql.log')).write_text(output)
        match=re.search(marker+r' pass=\d+ fail=0(?: not_run=0)?',output)
        check(name+' SQL regressions pass',process.returncode==3 and match is not None and re.search(r'not_run=[1-9]',output) is None);sql_results.append(match.group(0))
    fixture=dict(tenant=tenant,foreign=foreign,admin=accounts['admin']['id'],operator=accounts['operator']['id'],viewer=accounts['viewer']['id'],outsider=accounts['outsider']['id'],case=cases['01'])
    process=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1'],input="BEGIN; SELECT set_config('cw.core_fixture',"+lit(json.dumps(fixture))+",true);\n"+Path('e2e/core-operational-rls.sql').read_text()+"\nROLLBACK;",text=True,capture_output=True)
    output=process.stdout+process.stderr;(logs/'core-operational-sql.log').write_text(output)
    match=re.search(r'CW_CORE_OPERATIONAL_RESULTS pass=\d+ fail=0',output)
    check('Core SQL roles/RLS/immutability regressions pass',process.returncode==0 and match is not None);sql_results.append(match.group(0))
    check('all SQL probes roll back customer data and history',snapshot(upstream+['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs'])==before_sql)
    jobs=read('cw_notification_jobs');plans=read('cw_operational_events','command=eq.plan')
    check('documented plan outbox has exactly one pending job per plan and no delivery',len(jobs)==len(plans)==7 and {j['source_id'] for j in jobs}=={p['id'] for p in plans} and all(j['source_kind']=='core' and j['status']=='pending' and j['attempts']==0 for j in jobs) and read('cw_notifications')==[] and read('cw_notification_attempts')==[])
    counts=dict(customers=len(read('subjects')),measurements=len(read('observations')),c02_runs=len(read('c02_runs')),c03_bundles=len(read('c03_bundles')),c04_configurations=len(read('c04_configurations')),c04_evaluations=len(read('c04_evaluations')),cases=len(read('cw_operational_cases')),events=len(read('cw_operational_events')),cycles=len(read('cw_operational_cycles')))
    check('predetermined final record counts',counts==dict(customers=8,measurements=50,c02_runs=17,c03_bundles=17,c04_configurations=9,c04_evaluations=17,cases=6,events=51,cycles=8))
    summaries={}
    for cid,c in scenarios.items():
        actual=current(cid)['state'] if cid in cases else 'blocked'
        check('predefined final state '+cid,actual==c['final'])
        cycles=len(read('cw_operational_cycles','case_id=eq.'+cases[cid])) if cid in cases else 0
        check('predefined cycle count '+cid,cycles==c['cycles'])
        summaries[cid]=dict(scenario=c['scenario'],mode=c['mode'],expected=c,obtained=dict(c04=inputs[cid]['initial']['result'],documentary_state=inputs[cid]['initial']['state'],final_state=actual,cycles=cycles),inputs=inputs[cid],case=cases.get(cid))
        if cid in cases:
            h=history(cid);last=next((e for e in read('cw_operational_events','case_id=eq.'+cases[cid]+'&command=eq.decide&order=sequence.desc')[:1]),None)
            summaries[cid]['last_decision']=dict(result=last['to_state'],reasons=last['details']['reasons']) if last else None
            if c['decision']:check('predetermined last decision '+cid,last['to_state']==c['decision'])
    unchanged()
    report=dict(mission='20.4',base_main_commit=plan['base_main_commit'],executed_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),as_of=date(0),company=plan['company'],scenarios=summaries,counts=counts,
        opened_cases=6,blocked_entries=2,closed_cases=1,open_cases=5,retrospective_fixture_cases=3,prospective_cases=3,
        c01_requests=len(requests),measurement_presentations=sum(r['rows'] for r in requests),unique_measurements=50,idempotent_measurement_replays=12,measurement_rejections=0,
        assertions_passed=len(checks),checks=checks,sql_regressions=sql_results,negative_tests=negative,unchanged_tables=untouched_tables,
        limitations=plan['limitations'],product_defects_found=0,clock_modified=False,hosted_access=False,external_actions=False)
    (logs/'core-operational-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (logs/'core-operational-evidence.json').write_text(json.dumps({t:read(t) for t in upstream+['cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_notification_jobs']},indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['scenarios','checks','negative_tests','unchanged_tables']},ensure_ascii=False,indent=2))
finally:
    (logs/'core-operational-c01-requests.json').write_text(json.dumps(requests,indent=2)+'\n')
    server.terminate();server.wait(timeout=10);server_log.close()
