"""Mission 20.5: continuous monitoring, 100 SaaS clients and real pg_cron.

Requires a fresh labelled tmpfs stack from start_backend.py --local-mvp.
Expected values live in monitoring-100-plan.json, fixed before any measurements.
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
plan = json.loads(Path('e2e/monitoring-100-plan.json').read_text())
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
        text=True, capture_output=True, check=True,env={k:v for k,v in os.environ.items() if k not in ['PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGHOSTADDR','PGOPTIONS']}).stdout.strip()

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
    if 'limit=' in query:
        status, result=rest('/rest/v1/'+table+'?'+query,role=role,method='GET')
        assert status==200,(table,status,result)
        return result
    order='' if 'order=' in query else '&order='+({'cw_review_scans':'tenant_id','cw_notification_reads':'notification_id,recipient_id'}.get(table,'id'))
    rows=[]
    for offset in range(0,50000,200):
        status,page=rest('/rest/v1/'+table+'?'+query+order+'&limit=200&offset='+str(offset),role=role,method='GET')
        assert status==200,(table,status,page)
        rows.extend(page)
        if len(page)<200:return rows
    raise AssertionError('Unexpected table size; refusing silent truncation')

assert sql('SELECT count(*) FROM subjects')=='0','Fresh disposable database required'
assert sql("SELECT extversion FROM pg_extension WHERE extname='pg_cron'"),'Real pg_cron required'
timings=[];attempts=[];failures=[];wave_results={};business_tables=['observations','c02_runs','c02_results','c03_bundles','c03_indicators','c03_refs','c04_configurations','c04_evaluations','cw_operational_cases','cw_operational_events','cw_operational_cycles','cw_cases','cw_case_events','tenant_value_profiles','profile_indicators']
def timed(label,fn):
    start=time.perf_counter();result=fn();timings.append(dict(operation=label,seconds=round(time.perf_counter()-start,6)));return result
def snapshot(tables=business_tables):
    return json.loads(sql('SELECT jsonb_object_agg(name,hash) FROM ('+' UNION ALL '.join("SELECT "+lit(t)+" name,md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),'[]')::text) hash FROM public.\""+t+'" x' for t in tables)+') x'))
for role in ['admin','operator_a','operator_b','viewer','outsider']:
    a=dict(email='monitor-20-5-'+role+'@example.invalid',password=secrets.token_urlsafe(30)+'-Aa1!')
    assert rest('/auth/v1/signup',a,role)[0]==200
    s,r=rest('/auth/v1/token?grant_type=password',a,role);assert s==200 and r['user']['email_confirmed_at']
    a['id']=r['user']['id'];accounts[role]=a;sessions[role]=r['access_token']
p=private/'monitoring-100-accounts.json';p.write_text(json.dumps(accounts));p.chmod(0o600)
tenant=rpc('create_tenant',dict(_name=plan['company'],_subject_unit_type='organization'))
foreign=rpc('create_tenant',dict(_name=plan['foreign_company'],_subject_unit_type='organization'),'outsider')
for role in ['operator_a','operator_b','viewer']:rpc('add_tenant_member',dict(_tenant_id=tenant,_user_id=accounts[role]['id'],_role='operator' if role.startswith('operator') else role))
companies={};definitions={};configs={};subjects={};baseline={};cases={};groups={n:g for g in plan['groups'] for n in range(g['ids'][0],g['ids'][1]+1)}
indicators=json.loads(Path('e2e/integrated-value-plan.json').read_text())['indicators']
for scope,t,count,role in [('primary',tenant,100,'admin'),('foreign',foreign,3,'outsider')]:
    profile=rpc('create_value_profile_draft',dict(_tenant_id=t,_promise='[SYNTHETIC] Reporting automation; human confirmed individual goals',_expected_outcome='Per-indicator numeric goals, no global promise inference'),role)
    for original in indicators:
        i={**original,'observation_window_days':1,'comparison_window_days':1,'min_denominator':1,'baseline_min_period_days':1,'tenant_id':t,'profile_id':profile}
        assert rest('/rest/v1/profile_indicators',i,role)[0]==201
    rpc('approve_value_profile',dict(_profile_id=profile),role)
    rows=[dict(tenant_id=t,external_ref=scope+'-'+str(n).zfill(3),display_name='[SYNTHETIC] '+scope+' customer '+str(n).zfill(3)) for n in range(1,count+1)]
    s,created=rest('/rest/v1/subjects?select=id,external_ref',rows,role);assert s==201
    for c in created:subjects[scope,int(c['external_ref'].split('-')[1])]=c['id']
    cred=rpc('create_ingestion_credential',dict(_tenant_id=t,_name='[SYNTHETIC] '+scope+' HTTP waves',_source=plan['source'],_expires_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),_operation_id=newid()),role)
    companies[scope]=dict(tenant=t,profile=profile,credential=cred,role=role,count=count)
    for n in range(1,count+1):
        for key in plan['indicators']:
            d=dict(promise='[SYNTHETIC] Documented reporting workflow',promise_ref='urn:pulse:promise:v1',plan_capability='[SYNTHETIC] Reporting automation and delivery monitoring',plan_ref='urn:pulse:plan:v1',customer_goal='[SYNTHETIC] '+key+' goal in each of two daily windows',customer_ref='urn:pulse:'+scope+':'+str(n)+':'+key,compatibility='compatible',compatibility_ref='urn:pulse:human-review:v1',unit='min' if key=='cycle_minutes' else '%',source=plan['source'],aggregation='mean',comparator='lte' if key=='cycle_minutes' else 'gte',target=60 if key=='cycle_minutes' else 95,deadline=date(-10),observation_start=date(-20),window_count=2)
            cfg=rpc('save_c04_configuration',dict(_tenant_id=t,_subject_id=subjects[scope,n],_profile_id=profile,_indicator_key=key,_previous_id=None,_operation_id=newid(),_definition=d),role)
            configs[scope,n,key]=cfg;definitions[scope,n,key]=d
check('exactly 100 primary customers and three isolation controls',len(read('subjects'))==100 and len(read('subjects',role='outsider'))==3)
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(private/'ingestion-key.pem'),'-out',str(private/'ingestion-cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(private/'ingestion-key.pem').chmod(0o600)
ca=str(private/'ingestion-cert.pem');endpoint='https://127.0.0.1:54443/functions/v1/ingest-v1/observations'
log=open(logs/'monitoring-100-http.log','w');server=subprocess.Popen(['bun','run','e2e/ingestion-server.ts'],stdout=log,stderr=subprocess.STDOUT)
def row(scope,n,key,day,value,corrects=None):
    r=dict(subject_external_ref=scope+'-'+str(n).zfill(3),indicator_key=key,observed_at=date(day),value_numeric=str(value),unit='min' if key=='cycle_minutes' else '%',idempotency_key=newid())
    if corrects:r['corrects_observation_id']=corrects
    return r

def ingest(scope,rows,label,operation=None):
    c=companies[scope];before=snapshot(business_tables[1:])
    s,r,_=timed('C01 '+label,lambda:send(endpoint,c['credential']['secret'],dict(profile_id=c['profile'],source=plan['source'],coverage=dict(start=date(-20),end=date(1),declared=True),rows=rows),operation or newid(),ca))
    requests.append(dict(scope=scope,wave=label,rows=len(rows),status=s,result=r))
    assert s==200 and r['status']=='completed' and r['rejected']==0,(s,r)
    check('C01 '+label+' never analyses or changes human decisions',snapshot(business_tables[1:])==before);return r

def ingest_chunks(scope,rows,label):
    for start in range(0,len(rows),100):ingest(scope,rows[start:start+100],label)

def analyse(scope,n,as_of):
    c=companies[scope];role=c['role'];t=c['tenant']
    run=rpc('run_deterioration_analysis',dict(_tenant_id=t,_subject_id=subjects[scope,n],_expected_profile_id=c['profile'],_as_of=as_of),role)
    b=rpc('build_evidence_bundle',dict(_tenant_id=t,_run_id=run['run_id']),role)
    out={}
    for key in plan['indicators']:
        eid=rpc('evaluate_c04_configuration',dict(_tenant_id=t,_configuration_id=configs[scope,n,key],_bundle_id=b['bundle_id']),role)
        e=read('c04_evaluations','id=eq.'+eid,role)[0]
        signal=read('c02_results','run_id=eq.'+run['run_id']+'&indicator_key=eq.'+key,role)[0]
        check('explicit analysis preserves no causal/global promise claim',e['details']['causality']=='not_established' and e['details']['promise_fulfillment']=='not_determined')
        out[key]=dict(c02=signal['status'],c04=e['result'],evaluation=eid)
    return dict(run=run['run_id'],bundle=b['bundle_id'],indicators=out)

def paginate(name,t,role='admin',limit=17,**filters):
    result=[];cursor='';pages=0
    while True:
        p=timed(name+' page',lambda:rpc(name,dict(_tenant_id=t,_limit=limit,_after=cursor,**filters),role));pages+=1
        result.extend(p['items'])
        if not p['has_more']:break
        check(name+' cursor progresses',p['next_cursor'] and p['next_cursor']!=cursor);cursor=p['next_cursor']
        assert pages<100
    check(name+' complete pagination has no repeated keys',len({i['entry_key'] for i in result})==len(result));return result

def prepare(t=tenant,op=None,role='operator_a'):
    r=timed('manual review page',lambda:rpc('prepare_scheduled_reviews',dict(_tenant_id=t,_operation_id=op or newid()),role))
    check('review page uses <=50 references and real human actor',r['processed']<=50 and r['actor_kind']=='human' and r['actor_id']==accounts[role]['id'])
    attempts.append(r);return r

def cycle(t=tenant,role='operator_a'):
    old=rpc('scheduled_reviews',dict(_tenant_id=t),role)['scan']['last_cycle_at']
    for _ in range(25):
        r=prepare(t,role=role);assert r['status']=='completed',r
        if rpc('scheduled_reviews',dict(_tenant_id=t),role)['scan']['last_cycle_at']!=old:return
    raise AssertionError('Bounded review cursor failed to complete')

def flush(t=tenant,role='operator_a'):
    total=0
    for _ in range(160):
        r=timed('notification batch',lambda:rpc('prepare_operational_notifications',dict(_tenant_id=t),role));check('notification batch <=25',0<=r['processed']<=25);total+=r['processed']
        if r['processed']==0:return total
    raise AssertionError('Notification backlog not drained')

def invariant(label):
    before=snapshot();yield_state=label
    return before

def monitor_phase(label):
    before=snapshot();cycle();cycle();flush();check(label+' monitoring preserves all C01-C10 decisions and evidence',snapshot()==before)
    items=paginate('scheduled_reviews',tenant)
    active=[i for i in items if i['facts']['status']!='retired']
    axes={(i['subject_id'],i['indicator_key']) for i in active if i['source']['kind']=='measurement'}
    expected={(subjects['primary',n],k) for n in range(1,101) for k in plan['indicators']}
    check(label+' every customer and measurement axis remains visible',axes==expected and len(axes)==200)
    check(label+' all current sources refreshed',not any(i['needs_refresh'] for i in active))
    return items

def command(n,name,payload,role='operator_a'):
    c=read('cw_operational_cases','id=eq.'+cases[n])[0]
    return rpc('command_operational_case',dict(_tenant_id=tenant,_case_id=cases[n],_expected_version=c['version'],_operation_id=newid(),_command=name,_payload=payload),role)
def inbox(role,limit=13):
    rows=[];before=None;bid=None
    while True:
        a=dict(_tenant_id=tenant,_limit=limit)
        if before:a.update(_before=before,_before_id=bid)
        p=rpc('notification_inbox',a,role);rows.extend(p['items'])
        if not p['has_more']:break
        before=p['items'][-1]['created_at'];bid=p['items'][-1]['id']
    check('private inbox pagination has no duplicate notification',len({n['id'] for n in rows})==len(rows));return rows

def assignment(n,target,op=None,revision=None):
    current=rpc('case_responsibility',dict(_tenant_id=tenant,_case_id=cases[n]))['current']
    return dict(_tenant_id=tenant,_case_id=cases[n],_assignee_id=accounts[target]['id'] if target else None,_reason='[SYNTHETIC] Explicit responsibility for individual case',_reference='urn:pulse:assignment:v1',_expected_revision=revision if revision is not None else (current['revision'] if current else 0),_operation_id=op or newid())
def duplicates():
    return sql("SELECT count(*) FROM (SELECT tenant_id,recipient_membership_id,source_kind,source_id,kind FROM cw_notifications GROUP BY 1,2,3,4,5 HAVING count(*)>1) x")=='0'
def collect_history():return {t:{r['id']:r for r in read(t)} for t in business_tables if t not in ['cw_operational_cases']}
try:
    for _ in range(100):
        try:
            conn=http.client.HTTPSConnection('127.0.0.1',54443,context=ssl.create_default_context(cafile=ca),timeout=1);conn.request('GET','/functions/v1/ingest-v1/observations');s=conn.getresponse().status;conn.close()
            if s==405:break
        except OSError:pass
        time.sleep(.1)
    else:raise AssertionError('C01 HTTPS not ready')
    for scope,c in companies.items():
        rows=[row(scope,n,key,day,value) for n in range(1,c['count']+1) for key in plan['indicators'] for day,value in zip([-6,-5,-4],[100,95,90] if key=='cycle_minutes' else [98,98,98],strict=True)]
        ingest_chunks(scope,rows,'baseline')
        if scope=='primary':
            stable=rows[:100];op=newid();ingest(scope,stable,'baseline row replay',op);ingest(scope,stable,'baseline request replay',op)
        for n in range(1,c['count']+1):baseline[scope,n]=analyse(scope,n,date(-3))
    check('baseline primary and foreign measurement counts',len(read('observations'))==600 and len(read('observations',role='outsider'))==18)
    check('baseline ingestion/evaluation never opens cases',read('cw_operational_cases')==[])
    opening=dict(eligible=True,configuration_pinned=True,eligibility_reason='[SYNTHETIC] Administrator permits individual review of measured goal gap',eligibility_ref='urn:pulse:eligibility:v1',opening_criteria='Conclusive compatible individual C04 and explicit human review',closure_criteria='Historical individual goal, sufficient post-execution windows, no unresolved relevant data and documented human review',closure_ref='urn:pulse:closure:v1')
    for n in range(1,11):
        cases[n]=rpc('open_operational_case',dict(_tenant_id=tenant,_evaluation_id=baseline['primary',n]['indicators']['cycle_minutes']['evaluation'],_operation_id=newid(),_definition=opening))
        a=assignment(n,'operator_a' if n<=5 else 'operator_b')
        if n==1:
            with concurrent.futures.ThreadPoolExecutor(4) as pool:out=list(pool.map(lambda _:rpc('assign_operational_case',a),range(4)))
            check('concurrent responsibility replay creates one revision',len(set(out))==1)
        else:rpc('assign_operational_case',a)
        check('assignment replay is idempotent',rpc('assign_operational_case',a)==rpc('case_responsibility',dict(_tenant_id=tenant,_case_id=cases[n]))['current']['id'])
        if n<=9:
            proof=next(o['id'] for o in read('observations','subject_id=eq.'+subjects['primary',n]) if o['indicator_key']=='cycle_minutes' and instant(o['observed_at'])==instant(date(-6)))
            command(n,'investigate',dict(status='confirmed',finding='[SYNTHETIC] Human interpretation of a recorded workflow fact, without causal inference',reference='urn:pulse:investigation:v1',observation_ids=[proof]))
            command(n,'plan',dict(action='[SYNTHETIC] Human test checklist; no external actions',rationale='Bounded proposal',success_conditions='Historical goal and later sufficient evidence',limitations='No causal claim',reversal='Human review before restoring configuration',reference='urn:pulse:plan:v1',observation_seconds=3))
        if n in [6,7,8,9]:
            command(n,'approve',dict(valid_until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),reason='[SYNTHETIC] Human authorization of this plan',reference='urn:pulse:approval:v1'),'admin')
            command(n,'record_execution',dict(receipt='[SYNTHETIC] Human records a test checklist, no external change certified',reference='urn:pulse:receipt:v1'))
    after9=analyse('primary',9,date(-2))
    execution=read('cw_operational_events','case_id=eq.'+cases[9]+'&command=eq.record_execution')[0]
    while dt.datetime.now(dt.timezone.utc)<instant(execution['details']['wait_until']):time.sleep(.05)
    command(9,'observe',dict(bundle_id=after9['bundle']))
    command(9,'decide',dict(close_requested=True,criteria_met=True,material_contradiction=False,reason='[SYNTHETIC] Insufficient post-execution evidence requires continuity',reference='urn:pulse:decision:v1'),'admin')
    command(9,'start_cycle',dict(reason='[SYNTHETIC] Human starts independent cycle',reference='urn:pulse:cycle:v1'),'admin')
    c=read('cw_operational_cases','id=eq.'+cases[9])[0]
    denied=rest('/rest/v1/rpc/command_operational_case',dict(_tenant_id=tenant,_case_id=cases[9],_expected_version=c['version'],_operation_id=newid(),_command='record_execution',_payload=dict(receipt='x',reference='urn:pulse:denied')),'operator_b')
    check('new cycle inherits no authorization',denied[0]==400 and denied[1]['message']=='valid_authorization_required')
    check('all 100 customers in Central without silent truncation',len({x['subject_id'] for x in paginate('core_followup_queue',tenant)})==100)
    frozen=collect_history();case_projection=read('cw_operational_cases','order=id')
    print('BASELINE READY: 100 clients, 200 indicators, 10 human-opened cases; scheduling real cron.',flush=True)
    # Install the exact existing once-per-minute job twice: no second scheduler or duplicate job.
    sql(Path('scripts/monitoring/install-cron.sql').read_text());sql(Path('scripts/monitoring/install-cron.sql').read_text())
    job_command=sql("SELECT command FROM cron.job WHERE jobname='centerway-prepare-reviews-v1'")
    check('regression: background worker uses implicit transaction with local timeout and restricted role',not re.search(r'\b(BEGIN|COMMIT)\b',job_command,re.I) and "SET LOCAL statement_timeout='45s'" in job_command and 'SET LOCAL ROLE centerway_review_scheduler' in job_command)
    check('idempotent installation schedules one real minute job',sql("SELECT count(*) FROM cron.job WHERE jobname='centerway-prepare-reviews-v1' AND schedule='* * * * *' AND active")=='1')
    job_id=int(sql("SELECT jobid FROM cron.job WHERE jobname='centerway-prepare-reviews-v1'"));cron_start=time.perf_counter();cron_runs=[]
    before_cron=snapshot()
    while time.perf_counter()-cron_start<150:
        cron_runs=json.loads(sql('SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY runid),\'[]\') FROM cron.job_run_details r WHERE jobid='+str(job_id)))
        assert not any(r['status']=='failed' for r in cron_runs),cron_runs
        if sum(r['status']=='succeeded' for r in cron_runs)>=2:break
        time.sleep(1)
    else:raise AssertionError('Two actual pg_cron runs did not complete in 150 seconds')
    check('two actual minute pg_cron runs succeeded',sum(r['status']=='succeeded' for r in cron_runs)==2)
    minute_runs=cron_runs.copy()
    # Same real job/command, explicitly accelerated technical test cadence, not
    # a business clock change or another scheduler. Complete all 100 customers.
    sql('SELECT cron.schedule('+lit('centerway-prepare-reviews-v1')+','+lit('5 seconds')+','+lit(job_command)+')')
    full_start=time.perf_counter()
    while time.perf_counter()-full_start<100:
        finished=sql('SELECT count(*) FROM cw_review_scans WHERE last_cycle_at IS NOT NULL')=='2'
        running=sql('SELECT count(*) FROM cron.job_run_details WHERE jobid='+str(job_id)+" AND status IN ('starting','running')")!='0'
        if finished and not running:break
        time.sleep(.5)
    else:raise AssertionError('Real scheduler failed to complete all customers')
    sql('SELECT cron.unschedule('+str(job_id)+')')
    cron_runs=json.loads(sql('SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY runid),\'[]\') FROM cron.job_run_details r WHERE jobid='+str(job_id)))
    check('full real scheduler coverage has no infrastructure failure',all(r['status']=='succeeded' for r in cron_runs))
    check('real scheduler covers all primary references before any manual preparation',sql('SELECT count(*) FROM cw_review_entries WHERE tenant_id='+lit(tenant))=='401')
    cron_seconds=round(time.perf_counter()-cron_start,3)
    check('actual cron preserves C01-C10 history and decisions',snapshot()==before_cron)
    cron_attempts=read('cw_review_attempts','actor_kind=eq.scheduler')+read('cw_review_attempts','actor_kind=eq.scheduler',role='outsider')
    check('actual scheduler acts without impersonating humans',len(cron_attempts)>=4 and all(a['actor_id'] is None and a['processed']<=50 and a['status']=='completed' for a in cron_attempts))
    check('actual cron attempts fall within recorded infrastructure runs',all(any(instant(r['start_time'])-dt.timedelta(seconds=1)<=instant(a['started_at'])<=instant(r['end_time'])+dt.timedelta(seconds=1) for r in cron_runs if r['status']=='succeeded') for a in cron_attempts))
    print('REAL CRON PASSED: two natural minute ticks, sanitized scheduler actors and bounded cursor progress.',flush=True)
    # Complete remaining pages manually, distinguishing real HTTP operator preparation.
    initial=monitor_phase('baseline');cycle(foreign,'outsider');flush(foreign,'outsider')
    check('baseline has 401 independent active references',len([i for i in initial if i['facts']['status']!='retired'])==401)
    for n in [6,7,8]:
        e=next(i for i in initial if i['source'].get('case_id')==cases[n])
        check('elapsed C08 prepares review without proving recovery',e['facts']['status']=='available' and 'observation_window_elapsed_not_proof' in e['facts']['reasons'])
    protected_reviews={t:read(t) for t in ['cw_review_events','cw_review_attempts']}
    notification_rows=read('cw_notifications')
    for n in range(1,6):check('plan and review produce one authorization notice to admin '+str(n),len([x for x in notification_rows if x['case_id']==cases[n] and x['kind']=='authorization_needed' and x['recipient_id']==accounts['admin']['id']])==1)
    for n in [6,7,8]:check('observation notice goes to valid responsible operator',len([x for x in read('cw_notifications',role='operator_b') if x['case_id']==cases[n] and x['kind']=='observation_ended'])==1)
    check('no duplicate baseline notification occurrences',duplicates())
    # Identical repeated cycles create neither material revisions nor notifications.
    events_before=sql('SELECT count(*) FROM cw_review_events');notifications_before=sql('SELECT count(*) FROM cw_notifications')
    monitor_phase('unchanged repeat')
    check('unchanged sources do not invent review revisions',sql('SELECT count(*) FROM cw_review_events')==events_before)
    check('unchanged sources do not duplicate notifications',sql('SELECT count(*) FROM cw_notifications')==notifications_before)
    operation=newid()
    with concurrent.futures.ThreadPoolExecutor(4) as pool:out=list(pool.map(lambda _:rpc('prepare_scheduled_reviews',dict(_tenant_id=tenant,_operation_id=operation),'operator_a'),range(4)))
    check('four identical manual calls advance only one page',all(r==out[0] for r in out) and sql('SELECT count(*) FROM cw_review_attempts WHERE id='+lit(operation))=='1')
    # First changed wave is only C01; pending evidence cannot silently run analyses or Core.
    rows=[]
    for n in range(1,101):
        g=groups[n]
        rows.extend(row('primary',n,'cycle_minutes',d,v) for d,v in zip([-3,-2,-1],g['values'],strict=True) if v is not None)
        if 'delivery_values' in g:rows.extend(row('primary',n,'delivery_pct',d,v) for d,v in zip([-3,-2,-1],g['delivery_values'],strict=True))
    check('predefined wave has 320 measurements',len(rows)==320)
    ingest_chunks('primary',rows,'wave 1 changes')
    stale=paginate('scheduled_reviews',tenant)
    check('new C01 data flags every primary customer for refreshing',{i['subject_id'] for i in stale if i['needs_refresh']}=={subjects['primary',n] for n in range(1,101)})
    changed=monitor_phase('new unanalysed measurements')
    axes={(i['subject_id'],i['indicator_key']):i for i in changed if i['source']['kind']=='measurement'}
    for n in range(1,101):
        check('new primary evidence requests review '+str(n),'new_measurements_not_analysed' in axes[subjects['primary',n],'cycle_minutes']['facts']['reasons'])
        check('independent delivery reasons remain indicator-specific '+str(n),('new_measurements_not_analysed' in axes[subjects['primary',n],'delivery_pct']['facts']['reasons'])==(n>=81))
    # Only these explicit authorized RPC calls turn raw measurements into evaluations.
    for n in range(1,101):
        r=timed('explicit C02-C04 analysis',lambda n=n:analyse('primary',n,date(0)));g=groups[n];wave_results[n]=r
        check('predefined C02 classification '+str(n),r['indicators']['cycle_minutes']['c02']==g['c02'])
        check('predefined C04 outcome '+str(n),r['indicators']['cycle_minutes']['c04']==g['c04'])
        if n>=81:check('independent delivery deteriorates without changing primary result',r['indicators']['delivery_pct']['c02']==g['delivery_c02'] and r['indicators']['delivery_pct']['c04']==g['delivery_c04'])
    check('apparent recovery never closes or opens a case automatically',read('cw_operational_cases','order=id')==case_projection)
    analysed=monitor_phase('explicit analysed changes')
    check('all 410 expected current references survive explicit evaluations',len([i for i in analysed if i['facts']['status']!='retired'])==410)
    # Delayed measurements arrive through C01 after the earlier cutoff; no backdating ingested_at.
    ingest_chunks('primary',[row('primary',n,'cycle_minutes',-1,80) for n in range(61,81)],'late wave')
    late_pending=monitor_phase('late unanalysed evidence')
    for n in range(61,81):
        r=analyse('primary',n,date(0));g=groups[n]
        check('late wave resolves measured insufficiency but not the goal',r['indicators']['cycle_minutes']['c02']==g['after_late_c02'] and r['indicators']['cycle_minutes']['c04']==g['after_late_c04'])
        wave_results[n]['after_late']=r
    monitor_phase('late evidence explicitly analysed')
    corrected=[]
    for n in range(1,11):
        original=next(o for o in read('observations','subject_id=eq.'+subjects['primary',n]) if o['indicator_key']=='cycle_minutes' and instant(o['observed_at'])==instant(date(-1)))
        corrected.append(row('primary',n,'cycle_minutes',-1,50,original['id']))
    ingest_chunks('primary',corrected,'correction wave')
    monitor_phase('corrected unanalysed evidence')
    for n in range(1,11):
        r=analyse('primary',n,date(0));check('correction removes persistence but does not demonstrate goal',r['indicators']['cycle_minutes']['c02']=='no_deterioration' and r['indicators']['cycle_minutes']['c04']=='not_achieved');wave_results[n]['after_correction']=r
    monitor_phase('corrections explicitly analysed')
    print('WAVES PASSED: 950 primary observations, independent classifications, 100/100 customer coverage.',flush=True)
    # Concurrent ownership changes are explicit decisions, not authorizations to act.
    before_responsibility=snapshot();rev=rpc('case_responsibility',dict(_tenant_id=tenant,_case_id=cases[10]))['current']['revision']
    competing=[assignment(10,'operator_a',revision=rev),assignment(10,None,revision=rev)]
    with concurrent.futures.ThreadPoolExecutor(2) as pool:out=list(pool.map(lambda a:rest('/rest/v1/rpc/assign_operational_case',a),competing))
    check('competing assignments yield one explicit revision and one 409',sorted(s for s,r in out)==[200,409])
    rpc('assign_operational_case',assignment(10,'operator_b'))
    check('responsibility changes never authorize or change Core',snapshot()==before_responsibility)
    for role in ['operator_a','viewer','outsider','anon']:check(role+' cannot assign responsibility',rest('/rest/v1/rpc/assign_operational_case',assignment(10,'operator_a'),role)[0] in (401,403))
    for target in ['outsider','viewer']:check('assignment target must be authorized same-tenant member',rest('/rest/v1/rpc/assign_operational_case',assignment(10,target))[0]==400)
    # Fault injection uses test-only triggers on derived tables, with all guards enabled.
    monitor_tables=['cw_review_entries','cw_review_events','cw_review_scans','cw_review_attempts','cw_notification_jobs','cw_notifications','cw_notification_attempts']
    entries_before=snapshot(['cw_review_entries','cw_review_events'])
    sql("CREATE FUNCTION public.cw_m205_notify_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'PRIVATE_SYNTHETIC_NOTIFICATION_DETAIL' USING ERRCODE='P0952'; END $$; CREATE TRIGGER cw_m205_notify_fault BEFORE INSERT ON public.cw_notifications FOR EACH ROW EXECUTE FUNCTION public.cw_m205_notify_fault();")
    sql("CREATE SEQUENCE public.cw_m205_fault; CREATE FUNCTION public.cw_m205_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF nextval('public.cw_m205_fault')=2 THEN RAISE EXCEPTION 'PRIVATE_SYNTHETIC_SCAN_DETAIL' USING ERRCODE='P0951'; END IF; RETURN NEW; END $$; CREATE TRIGGER cw_m205_fault BEFORE UPDATE ON public.cw_review_entries FOR EACH ROW EXECUTE FUNCTION public.cw_m205_fault();")
    try:
        failed=prepare();check('catchable page failure persists sanitized SQLSTATE',failed['status']=='failed' and failed['error_code']=='P0951' and failed['processed']==0 and 'PRIVATE_SYNTHETIC' not in json.dumps(failed))
        check('partial page writes roll back and cursor does not advance',snapshot(['cw_review_entries','cw_review_events'])==entries_before and failed['cursor_after']==failed['cursor_before'])
        check('failed operation replay returns original failed attempt',rpc('prepare_scheduled_reviews',dict(_tenant_id=tenant,_operation_id=failed['id']))==failed)
        failures.append(dict(test='catchable partial page',attempt=failed['id'],code='P0951',recovered=True))
    finally:sql('DROP TRIGGER cw_m205_fault ON public.cw_review_entries; DROP FUNCTION public.cw_m205_fault(); DROP SEQUENCE public.cw_m205_fault;')
    try:
        rpc('prepare_operational_notifications',dict(_tenant_id=tenant))
        failed_jobs=read('cw_notification_jobs',"source_kind=eq.attempt&source_id=eq."+failed['id'])
        check('notification failure is identifiable and retains retry capability',len(failed_jobs)==1 and failed_jobs[0]['status']=='failed' and failed_jobs[0]['error_code']=='P0952' and failed_jobs[0]['attempts']==1)
        notify_retry=failed_jobs[0]['next_try_at'];notify_job=failed_jobs[0]['id']
        check('failure details never leak to inbox',not any('PRIVATE_SYNTHETIC' in json.dumps(i) for i in inbox('admin')))
    finally:sql('DROP TRIGGER cw_m205_notify_fault ON public.cw_notifications; DROP FUNCTION public.cw_m205_notify_fault();')
    recovered=prepare();check('new manual operation recovers failed scan',recovered['status']=='completed' and rpc('scheduled_reviews',dict(_tenant_id=tenant))['scan']['last_error'] is None)
    # Terminate a real uncommitted PostgreSQL transaction after it has prepared a page.
    # This SQL role/claim interruption probe is separate from the real HTTP logins above.
    interrupted_op=newid();before_interruption=snapshot(monitor_tables)
    proc=subprocess.Popen(['psql','-X','-qAt','-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    proc.stdin.write('BEGIN; SELECT pg_backend_pid();\n');proc.stdin.flush();pid=int(proc.stdout.readline())
    proc.stdin.write("SELECT set_config('request.jwt.claims',"+lit(json.dumps(dict(role='authenticated',sub=accounts['operator_a']['id'])))+",true); SET ROLE authenticated; SELECT public.prepare_scheduled_reviews("+lit(tenant)+','+lit(interrupted_op)+"); SELECT 'CW_PAGE_UNCOMMITTED';\n");proc.stdin.flush()
    for line in proc.stdout:
        if line.strip()=='CW_PAGE_UNCOMMITTED':break
    else:raise AssertionError('Interrupted page never reached uncommitted barrier')
    check('targeted backend really terminated',sql('SELECT pg_terminate_backend('+str(pid)+')')=='t');proc.stdin.close();proc.wait(timeout=10)
    check('termination rolls back all monitor and outbox writes',snapshot(monitor_tables)==before_interruption)
    check('interrupted attempt absent because transaction never committed',sql('SELECT count(*) FROM cw_review_attempts WHERE id='+lit(interrupted_op))=='0')
    retry=prepare(op=interrupted_op);check('same operation safely retries after interrupted transaction',retry['status']=='completed' and rpc('prepare_scheduled_reviews',dict(_tenant_id=tenant,_operation_id=interrupted_op))==retry)
    failures.append(dict(test='terminated uncommitted page',operation=interrupted_op,recovered=True,persisted_failure_attempt=False,infrastructure_evidence='targeted pg_terminate_backend and complete hash rollback'))
    # Concurrent worker calls here are direct restricted-role probes, NOT scheduled Cron runs.
    with concurrent.futures.ThreadPoolExecutor(4) as pool:worker_results=list(pool.map(lambda _:json.loads(sql('SET ROLE centerway_review_scheduler; SELECT public.process_review_schedule(2);')),range(4)))
    direct_attempts=[a for r in worker_results for a in r['attempts']]
    check('restricted worker concurrency remains bounded and non-human',all(a['processed']<=50 and a['actor_kind']=='scheduler' and a['actor_id'] is None for a in direct_attempts))
    # Permission, isolation and inbox pagination/read replay under real GoTrue tokens.
    for role in ['admin','operator_a','operator_b','viewer','outsider','anon']:check('HTTP cannot invoke private scheduler as '+role,rest('/rest/v1/rpc/process_review_schedule',dict(_limit=1),role)[0] in (401,403,404))
    for name in ['prepare_scheduled_reviews','scheduled_reviews','core_followup_queue','prepare_operational_notifications','notification_inbox']:
        a=dict(_tenant_id=tenant)
        if name=='prepare_scheduled_reviews':a['_operation_id']=newid()
        check('foreign company cannot call '+name,rest('/rest/v1/rpc/'+name,a,'outsider')[0]==403)
    for table in monitor_tables+['cw_case_assignments','cw_operational_cases','observations']:
        check('no cross-company table access '+table,read(table,'tenant_id=eq.'+tenant,'outsider')==[])
        for method,body in [('POST',{}),('PATCH',{'tenant_id':tenant}),('DELETE',None)]:check('direct '+method+' denied '+table,rest('/rest/v1/'+table+'?tenant_id=eq.'+tenant,body,method=method)[0]==403)
    check('viewer cannot prepare human review',rest('/rest/v1/rpc/prepare_scheduled_reviews',dict(_tenant_id=tenant,_operation_id=newid()),'viewer')[0]==403)
    check('viewer has no other peoples private notifications',inbox('viewer')==[])
    a_notices=inbox('operator_a');b_notices=inbox('operator_b');admin_notices=inbox('admin')
    check('private inboxes show only their actual recipient',all(n['recipient_id']==accounts[role]['id'] for role,rows in [('operator_a',a_notices),('operator_b',b_notices),('admin',admin_notices)] for n in rows))
    sample=a_notices[0]
    check('wrong recipient cannot mark another inbox read',rest('/rest/v1/rpc/mark_notification_read',dict(_tenant_id=tenant,_notification_id=sample['id']))[0]==403)
    for _ in range(2):rpc('mark_notification_read',dict(_tenant_id=tenant,_notification_id=sample['id']),'operator_a')
    check('read receipt is idempotent',sql('SELECT count(*) FROM cw_notification_reads WHERE notification_id='+lit(sample['id']))=='1')
    # Respect the existing one-minute retry interval naturally; never edit next_try_at.
    print('RECOVERY WAIT: notification retry becomes due at '+notify_retry+'; business clocks unchanged.',flush=True)
    until=instant(notify_retry);assert (until-dt.datetime.now(dt.timezone.utc)).total_seconds()<70
    while dt.datetime.now(dt.timezone.utc)<until:time.sleep(.5)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:out=list(pool.map(lambda _:rpc('prepare_operational_notifications',dict(_tenant_id=tenant)),range(4)))
    check('concurrent notification retry batches remain bounded',all(0<=r['processed']<=25 for r in out));flush()
    job=read('cw_notification_jobs','id=eq.'+notify_job)[0]
    check('notification recovers after real retry interval',job['status']=='completed' and job['attempts']==2)
    check('one failure occurrence produces one notification to admin',sql("SELECT count(*) FROM cw_notifications WHERE source_kind='attempt' AND source_id="+lit(failed['id'])+" AND kind='operational_failure' AND recipient_id="+lit(accounts['admin']['id']))=='1')
    failures.append(dict(test='notification delivery failure',job=notify_job,code='P0952',recovered=True,natural_retry_at=notify_retry,attempts=2))
    monitor_phase('final steady state')
    # Validate every persisted notification recipient from its original occurrence/assignment.
    notes=json.loads(sql("SELECT coalesce(jsonb_agg(to_jsonb(n)),'[]') FROM cw_notifications n WHERE tenant_id="+lit(tenant)));assignments={r['id']:r for r in read('cw_case_assignments')};assigned=list(assignments.values())
    for n in notes:
        if n['kind']=='case_assigned':expected=assignments[n['source_id']]['assignee_id']
        elif n['kind']=='responsibility_changed':
            current_assignment=assignments[n['source_id']];expected=next(a['assignee_id'] for a in assigned if a['case_id']==current_assignment['case_id'] and a['revision']==current_assignment['revision']-1)
        elif n['required_role']=='admin' or n['case_id'] is None:expected=accounts['admin']['id']
        else:
            prior=sorted((a for a in assigned if a['case_id']==n['case_id'] and instant(a['created_at'])<=instant(n['created_at'])),key=lambda a:a['revision'])
            expected=prior[-1]['assignee_id'] if prior and prior[-1]['assignee_id'] else accounts['admin']['id']
        check('notification recipient matches existing routing contract',n['recipient_id']==expected)
    for t,rows in protected_reviews.items():
        current_rows={r['id']:r for r in read(t)}
        check('initial immutable monitoring history preserved '+t,all(current_rows[r['id']]==r for r in rows))
    check('no duplicate occurrence/recipient notifications globally',duplicates())
    count=sql('SELECT count(*) FROM cw_notifications');flush();flush();check('empty retries cannot duplicate notifications',sql('SELECT count(*) FROM cw_notifications')==count)
    for t,old in frozen.items():
        actual={r['id']:r for r in read(t)}
        check('all prior immutable '+t+' rows preserved',all(actual[k]==v for k,v in old.items()))
    check('all original human case projections preserved across waves/workers',read('cw_operational_cases','order=id')==case_projection)
    check('no value conclusion without persisted historical evaluation',all(e['details']['promise_fulfillment']=='not_determined' and e['details']['causality']=='not_established' for e in read('c04_evaluations')))
    check('all C03 content hashes independently reconstruct',all(h['valid'] for h in json.loads(sql(Path('e2e/c03-verify-content.sql').read_text()))))
    check('exact final customer and observation counts',len(read('subjects'))==100 and len(read('subjects',role='outsider'))==3 and len(read('observations'))==950 and len(read('observations',role='outsider'))==18)
    check('no technical fault trigger remains',sql("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'cw_m205_%'")=='0')
    final_items=paginate('scheduled_reviews',tenant);check('all 100 customers and both axes remain covered at end',len({i['subject_id'] for i in final_items})==100 and len([i for i in final_items if i['source']['kind']=='measurement'])==200)
    before_reads=snapshot(monitor_tables+['cw_case_assignments']+business_tables)
    paginate('core_followup_queue',tenant);paginate('scheduled_reviews',tenant);inbox('admin');inbox('operator_a')
    check('all queue/history/inbox reads are side-effect free',snapshot(monitor_tables+['cw_case_assignments']+business_tables)==before_reads)
    # Existing regression suites, including SQL permission checks, always roll back.
    sql_results=[]
    for name,marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS'),('c03','CW_C03_RESULTS')]:
        r=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+name+'_test.sql'],text=True,capture_output=True);output=r.stdout+r.stderr;(logs/('monitoring-100-'+name+'-sql.log')).write_text(output)
        m=re.search(marker+r' pass=\d+ fail=0(?: not_run=0)?',output);check(name+' SQL regression',r.returncode==3 and m is not None and re.search(r'not_run=[1-9]',output) is None);sql_results.append(m.group(0))
    sql_probe=dict(tenant=tenant,admin=accounts['admin']['id'],operator=accounts['operator_a']['id'],viewer=accounts['viewer']['id'],outsider=accounts['outsider']['id'])
    p=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1'],input="BEGIN; SELECT set_config('cw.monitor_fixture',"+lit(json.dumps(sql_probe))+",true);\n"+Path('e2e/monitoring-100-rls.sql').read_text()+"\nROLLBACK;",text=True,capture_output=True)
    output=p.stdout+p.stderr;(logs/'monitoring-100-rls.log').write_text(output);m=re.search(r'CW_MONITOR_100_RESULTS pass=\d+ fail=0',output);check('monitoring SQL/RLS restricted capability',p.returncode==0 and m is not None);sql_results.append(m.group(0))
    # Actual timings, not a production SLA. No user-facing classifier is reimplemented.
    summary={}
    for label in sorted({t['operation'] for t in timings}):
        vals=sorted(t['seconds'] for t in timings if t['operation']==label);summary[label]=dict(calls=len(vals),total_seconds=round(sum(vals),4),median_seconds=vals[len(vals)//2],p95_seconds=vals[min(len(vals)-1,int(len(vals)*.95))],max_seconds=max(vals))
    counts={t:int(sql('SELECT count(*) FROM '+t+' WHERE tenant_id='+lit(tenant))) for t in ['observations','c02_runs','c03_bundles','c04_evaluations','cw_operational_cases','cw_operational_events','cw_review_entries','cw_review_events','cw_review_attempts','cw_case_assignments','cw_notifications','cw_notification_jobs','cw_notification_attempts']}
    report=dict(mission='20.5',base_main_commit=plan['base_main_commit'],executed_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),company=plan['company'],primary_customers=100,foreign_customers=3,measurement_axes=200,active_references=410,counts=counts,
        waves=wave_results,c01_http_requests=len(requests),measurement_presentations=sum(r['rows'] for r in requests),unique_measurements=968,measurement_rejections=0,
        cron=dict(extension=sql("SELECT extversion FROM pg_extension WHERE extname='pg_cron'"),schedule='* * * * *',minute_runs=minute_runs,full_cycle_test_schedule='5 seconds',actual_runs=cron_runs,actual_attempts=cron_attempts,infrastructure_timestamp_tolerance_ms=1000,wait_seconds=cron_seconds,manual_restricted_worker_attempts=direct_attempts),
        failures=failures,notification_kinds={k:sum(n['kind']==k for n in notes) for k in sorted({n['kind'] for n in notes})},duplicate_notifications=0,assertions_passed=len(checks),checks=checks,sql_regressions=sql_results,timings=summary,limitations=plan['limitations'],product_defects_found=1,hosted_access=False,business_clock_modified=False,automatic_interventions=False)
    (logs/'monitoring-100-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    evidence={t:read(t) for t in business_tables+monitor_tables+['cw_case_assignments']}
    evidence['cw_notifications']=notes  # Owner inspection of all synthetic recipients; HTTP privacy is tested separately.
    evidence['cw_notification_reads']=json.loads(sql("SELECT coalesce(jsonb_agg(to_jsonb(r)),'[]') FROM cw_notification_reads r WHERE tenant_id="+lit(tenant)))
    (logs/'monitoring-100-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['waves','checks','cron','timings']},ensure_ascii=False,indent=2),flush=True)
finally:
    # Stop only our disposable job, including on an assertion failure.
    sql("SELECT cron.unschedule(jobid) FROM cron.job WHERE jobname='centerway-prepare-reviews-v1'")
    (logs/'monitoring-100-c01-requests.json').write_text(json.dumps(requests,indent=2)+'\n')
    server.terminate();server.wait(timeout=10);log.close()
