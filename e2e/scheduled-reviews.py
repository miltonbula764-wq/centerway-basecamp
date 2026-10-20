"""Disposable PostgreSQL17 + real GoTrue/PostgREST; monitoring only. No hosted connection."""
import concurrent.futures
import json
import os
import re
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
import uuid

if os.environ.get('CW_LOCAL_MVP') == '1':
    info=json.loads(subprocess.check_output(['docker','inspect','cw-mvp-db']))[0]
    assert info['Config']['Image']=='postgres:17' and info['Config'].get('Labels',{}).get('centerway.disposable')=='mvp'
    assert '/var/lib/postgresql/data' in info['HostConfig'].get('Tmpfs',{})
    assert all(m['Type']=='tmpfs' for m in info.get('Mounts',[]))
    assert info['HostConfig']['PortBindings']['5432/tcp']==[{'HostIp':'127.0.0.1','HostPort':'5432'}]
else:
    assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
assert os.environ.get('PGHOST')=='127.0.0.1' and os.environ.get('PGDATABASE')=='cw_e2e'
env={k:v for k,v in os.environ.items() if k not in ('PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGHOSTADDR','PGOPTIONS')};env['PGPASSFILE']='/dev/null'
def sql(query):
    r=subprocess.run(['psql','-X','-qAt','-v','ON_ERROR_STOP=1'],input=query,text=True,capture_output=True,env=env)
    assert r.returncode==0,r.stderr
    return r.stdout.strip()
def lit(v):return "'"+str(v).replace("'","''")+"'"
newid=lambda:str(uuid.uuid4())
cfg=json.loads(Path('e2e/private/public.json').read_text());assert cfg['url']=='http://127.0.0.1:54321'
f=json.loads(Path('e2e/followup-fixtures.json').read_text());atlas=json.loads(Path('e2e/operational-fixtures.json').read_text());api=json.loads(Path('e2e/api-fixtures.json').read_text())
users=json.loads(Path('e2e/private/mvp-users.json').read_text());users['ownerB']=json.loads(Path('e2e/private/users.json').read_text())['ownerB']
def rest(path,body=None,role='admin',method='POST'):
    req=urllib.request.Request(cfg['url']+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Content-Type':'application/json','apikey':cfg['anon'],'Authorization':'Bearer '+(users[role]['token'] if role else cfg['anon'])})
    try:
        with urllib.request.urlopen(req,timeout=60) as r:return r.status,json.loads(r.read() or 'null')
    except urllib.error.HTTPError as r:return r.code,json.loads(r.read() or 'null')
def rpc(name,args,role='admin'):return rest('/rest/v1/rpc/'+name,args,role)
for role in users:
    s,r=rest('/auth/v1/token?grant_type=password',{'email':users[role]['email'],'password':users[role]['password']},None)
    assert s==200 and r['user']['email_confirmed_at'];users[role]['token']=r['access_token']
def prepare(tenant,role='admin',operation=None):
    return rpc('prepare_scheduled_reviews',{'_tenant_id':tenant,'_operation_id':operation or newid()},role)
def page(tenant,**kw):
    s,r=rpc('scheduled_reviews',{'_tenant_id':tenant,**kw});assert s==200,(s,r);return r
# Re-run previous security/SQL suites after 0020, not merely before the upgrade.
for suite, marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS'),('c03','CW_C03_RESULTS')]:
    r=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+suite+'_test.sql'],env=env,text=True,capture_output=True)
    output=r.stdout+r.stderr
    Path('e2e/logs/monitoring-regression-'+suite+'.log').write_text(output)
    assert r.returncode==3 and re.search(marker+r' pass=\d+ fail=0(?: |$)',output) and not re.search(r'not_run=[1-9]',output),suite+' regression failed (see log)'
    print(re.search(marker+r' pass=\d+ fail=0(?: not_run=0)?',output).group(0))
# ACL: no generic admin/service token or fabricated human session for the worker.
for role in ['admin','operator','viewer','ownerB',None]:
    assert rpc('process_review_schedule',{'_limit':1},role)[0] in (401,403,404)
for role in ['viewer','ownerB',None]:assert prepare(f['tenant'],role)[0] in (401,403)
assert rpc('scheduled_reviews',{'_tenant_id':f['tenant']},'ownerB')[0]==403
for table in ['cw_review_entries','cw_review_scans','cw_review_events','cw_review_attempts']:
    assert rest('/rest/v1/'+table+'?tenant_id=eq.'+f['tenant'],None,'ownerB','GET')[1]==[]
    assert rest('/rest/v1/'+table,{},'admin')[0]==403
    assert sql("SELECT relrowsecurity FROM pg_class WHERE oid="+lit('public.'+table)+"::regclass")=='t'
    assert sql("SELECT has_table_privilege('centerway_review_scheduler',"+lit(table)+",'SELECT')")=='f'
assert sql("SELECT has_function_privilege('service_role','public.process_review_schedule(integer)','EXECUTE')")=='f'
assert sql("SELECT has_function_privilege('centerway_review_scheduler','public.import_observations(uuid,uuid,text,timestamp with time zone,timestamp with time zone,boolean,text,jsonb)','EXECUTE')")=='f'
# Fingerprint every existing business table. Only the new monitoring tables may change.
tables=sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT LIKE 'cw_review_%' ORDER BY tablename").splitlines()
def snapshot():return [sql('SELECT md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),\'[]\')::text) FROM public."'+t+'" x') for t in tables]
before=snapshot()
# Concurrent replay: same operation returns one immutable attempt and one advancement.
op=newid()
with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:prepare(f['tenant'],'operator',op),range(4)))
assert all(s==200 and r==results[0][1] for s,r in results),results
assert sql('SELECT count(*) FROM cw_review_attempts WHERE id='+lit(op))=='1'
# Fully consume bounded pages without manipulating business time or deadlines.
def cycle(tenant):
    old=page(tenant)['scan']['last_cycle_at']
    for _ in range(40):
        s,r=prepare(tenant);assert s==200 and r['status']=='completed',(s,r);assert r['processed']<=50
        if page(tenant)['scan']['last_cycle_at']!=old:return
    raise AssertionError('cursor did not finish bounded cycle')
cycle(f['tenant']);cycle(atlas['tenant'])
all_items=[];cursor=''
while True:
    p=page(f['tenant'],_after=cursor,_limit=100);all_items+=p['items']
    if not p['has_more']:break
    cursor=p['next_cursor']
assert len(all_items)==612 and len({i['entry_key'] for i in all_items})==612
axes={i['indicator_key']:i for i in all_items if i['source']['kind']=='c04' and i['subject_id']==f['customer']['id']}
assert axes['contradiction_minutes']['facts']['status']=='pending'
assert axes['partial_minutes']['facts']['status']=='pending'
assert axes['independent_minutes']['facts']['status']=='available'
assert page(f['tenant'],_status='pending',_indicator='partial')['items']
assert page(atlas['tenant'],_indicator='cycle_minutes')['items']
# Existing API and CSV observations are recognized, with independent axes and no new engine.
assert sql('SELECT count(*) FROM observations WHERE subject_id='+lit(api['subject'])+' AND integration_credential_id IS NOT NULL')!='0'
assert sql('SELECT count(*) FROM observations WHERE subject_id='+lit(f['customer']['id'])+' AND integration_credential_id IS NULL')!='0'
api_entry=next(i for i in page(atlas['tenant'],_limit=100)['items'] if i['subject_id']==api['subject'] and i['indicator_key']=='cycle_minutes' and i['source']['kind']=='measurement')
assert 'documented_measurement_cadence_elapsed' in api_entry['facts']['reasons']
assert 'new_measurements_not_analysed' in api_entry['facts']['reasons']
# Idempotent complete scan: neither revisions nor immutable event count grows without source changes.
versions=sql('SELECT md5(jsonb_agg(jsonb_build_array(entry_key,revision) ORDER BY entry_key)::text) FROM cw_review_entries WHERE tenant_id='+lit(f['tenant']))
count=sql('SELECT count(*) FROM cw_review_events WHERE tenant_id='+lit(f['tenant']))
cycle(f['tenant'])
assert versions==sql('SELECT md5(jsonb_agg(jsonb_build_array(entry_key,revision) ORDER BY entry_key)::text) FROM cw_review_entries WHERE tenant_id='+lit(f['tenant']))
assert count==sql('SELECT count(*) FROM cw_review_events WHERE tenant_id='+lit(f['tenant']))
# Concurrent scheduler claims use SKIP LOCKED; work stays bounded, actor is explicitly non-human.
with concurrent.futures.ThreadPoolExecutor(4) as pool:
    out=list(pool.map(lambda _:sql('SET ROLE centerway_review_scheduler; SELECT public.process_review_schedule(2);'),range(4)))
for output in out:
    for attempt in json.loads(output)['attempts']:
        assert attempt['actor_kind']=='scheduler' and attempt['actor_id'] is None and attempt['processed']<=50 and attempt['status']=='completed'
# Inject a failure only in our disposable instance; SQLSTATE persisted, no message/secret leakage.
cycle(atlas['tenant'])
# Fault after the first actual entry update proves rollback of partial page progress.
entries_before=sql('SELECT md5(jsonb_agg(to_jsonb(e) ORDER BY id)::text) FROM cw_review_entries e WHERE tenant_id='+lit(atlas['tenant']))
sql("CREATE SEQUENCE public.cw_review_test_fault; CREATE FUNCTION public.cw_review_test_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF nextval('public.cw_review_test_fault')=2 THEN RAISE EXCEPTION 'synthetic private failure detail' USING ERRCODE='P0099'; END IF; RETURN NEW; END $$; CREATE TRIGGER cw_review_test_fault BEFORE UPDATE ON public.cw_review_entries FOR EACH ROW EXECUTE FUNCTION public.cw_review_test_fault();")
try:
    s,r=prepare(atlas['tenant']);assert s==200 and r['status']=='failed' and r['error_code']=='P0099' and r['processed']==0
    assert entries_before==sql('SELECT md5(jsonb_agg(to_jsonb(e) ORDER BY id)::text) FROM cw_review_entries e WHERE tenant_id='+lit(atlas['tenant']))
    failed=r['id'];assert prepare(atlas['tenant'],operation=failed)[1]==r
    assert page(atlas['tenant'])['scan']['last_error']=='P0099'
    assert 'synthetic private failure detail' not in json.dumps(r)
finally:sql("DROP TRIGGER cw_review_test_fault ON public.cw_review_entries; DROP FUNCTION public.cw_review_test_fault(); DROP SEQUENCE public.cw_review_test_fault;")
s,r=prepare(atlas['tenant']);assert s==200 and r['status']=='completed';assert page(atlas['tenant'])['scan']['last_error'] is None
assert sql('SELECT count(*) FROM cw_review_attempts WHERE id='+lit(failed)+" AND status='failed'")=='1'
# Reads do not change attempts, entries, events, or any existing business data.
monitor_before=sql("SELECT md5((SELECT jsonb_agg(to_jsonb(e) ORDER BY id)::text FROM cw_review_entries e)|| (SELECT jsonb_agg(to_jsonb(a) ORDER BY id)::text FROM cw_review_attempts a))")
for role in ['admin','operator','viewer']:
    assert rpc('scheduled_reviews',{'_tenant_id':f['tenant']},role)[0]==200
assert monitor_before==sql("SELECT md5((SELECT jsonb_agg(to_jsonb(e) ORDER BY id)::text FROM cw_review_entries e)|| (SELECT jsonb_agg(to_jsonb(a) ORDER BY id)::text FROM cw_review_attempts a))")
assert snapshot()==before,'monitoring modified existing C01-C10/team/credential data'
print('PASS monitoring: real Auth/RLS, admin/operator/viewer, tenant isolation, API+CSV sources, 612 independent entries, bounded pagination, concurrent replay/workers, immutable versions, failure rollback/retry, read-only Core preservation.')
# Extra temporal/source probes are rolled back. No clocks or existing immutable facts are edited.
fixture=lit(json.dumps(f))
sql("BEGIN; SELECT set_config('cw.monitor_fixture',"+fixture+",true);"+r'''
DO $test$
DECLARE f jsonb:=current_setting('cw.monitor_fixture')::jsonb;t uuid:=(f->>'tenant')::uuid;
 c public.c04_configurations;future uuid;past uuid;q jsonb;facts jsonb;fresh jsonb;answer jsonb;old_count integer;e record;
BEGIN
 SELECT * INTO c FROM public.c04_configurations WHERE tenant_id=t AND subject_id=(f->'customer'->>'id')::uuid AND indicator_key='independent_minutes' ORDER BY version DESC LIMIT 1;
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',f->>'actor')::text,true);
 SET LOCAL ROLE authenticated;
 future:=public.save_c04_configuration(t,c.subject_id,c.profile_id,c.indicator_key,c.id,gen_random_uuid(),c.definition||jsonb_build_object('deadline',clock_timestamp()+interval '1 day'));
 RESET ROLE;
 q:=jsonb_build_object('kind','c04','subject_id',c.subject_id,'indicator_key',c.indicator_key,'configuration_id',future);
 facts:=public._review_facts(t,q);
 IF (facts->>'review_at')::timestamptz<=clock_timestamp() OR facts->'reasons' ? 'documented_objective_deadline_reached' THEN RAISE EXCEPTION 'future deadline treated as elapsed'; END IF;
 SET LOCAL ROLE authenticated;
 past:=public.save_c04_configuration(t,c.subject_id,c.profile_id,c.indicator_key,future,gen_random_uuid(),c.definition||jsonb_build_object('deadline',clock_timestamp()-interval '1 second'));
 RESET ROLE;
 facts:=public._review_facts(t,q||jsonb_build_object('configuration_id',past));
 IF NOT facts->'reasons' ? 'documented_objective_deadline_reached' THEN RAISE EXCEPTION 'documented deadline missed'; END IF;
 -- A historical configuration with a newer version cannot become executable through monitoring.
 facts:=public._review_facts(t,q);
 IF facts->>'status'<>'pending' OR NOT facts->'reasons' ? 'configuration_revision_requires_review' THEN RAISE EXCEPTION 'historical guard lost'; END IF;
 -- Isolate this import: a pre-existing stale entry must not mask the bug.
 -- now()/ingested_at is earlier than checked_at in this same transaction.
 FOR e IN SELECT * FROM public.cw_review_entries WHERE tenant_id=t AND subject_id=c.subject_id AND indicator_key=c.indicator_key LOOP
  PERFORM public._review_store(t,e.source,public._review_facts(t,e.source),gen_random_uuid());
 END LOOP;
 SET LOCAL ROLE authenticated;
 answer:=public.scheduled_reviews(t,'','independent_minutes','',100);
 RESET ROLE;
 IF EXISTS(SELECT FROM jsonb_array_elements(answer->'items') x WHERE x->>'subject_id'=c.subject_id::text AND (x->>'needs_refresh')::boolean) THEN RAISE EXCEPTION 'fresh snapshot incorrectly marked stale'; END IF;
 -- Fresh CSV record after C02: real import contract, no direct observation writes.
 SET LOCAL ROLE authenticated;
 answer:=public.import_observations(t,c.profile_id,'synthetic-atlas',clock_timestamp()-interval '3 days',clock_timestamp(),true,'synthetic-monitoring.csv',jsonb_build_array(jsonb_build_object('line',1,'subject_external_ref',f->'customer'->>'external_ref','indicator_key','independent_minutes','observed_at',clock_timestamp()-interval '1 hour','value_numeric','70','unit','min','idempotency_key',gen_random_uuid())));
 RESET ROLE;
 IF answer->>'status'<>'completed' THEN RAISE EXCEPTION 'synthetic import failed %',answer; END IF;
 q:=jsonb_build_object('kind','measurement','subject_id',c.subject_id,'profile_id',c.profile_id,'indicator_key',c.indicator_key);
 fresh:=public._review_facts(t,q);
 IF NOT fresh->'reasons' ? 'new_measurements_not_analysed' THEN RAISE EXCEPTION 'new CSV measurement missed'; END IF;
 SET LOCAL ROLE authenticated;
 answer:=public.scheduled_reviews(t,'','independent_minutes','',100);
 RESET ROLE;
 IF NOT EXISTS(SELECT FROM jsonb_array_elements(answer->'items') x WHERE x->>'subject_id'=c.subject_id::text AND (x->>'needs_refresh')::boolean) THEN RAISE EXCEPTION 'stale snapshot not identified'; END IF;
 -- Refreshing the snapshot consumes the new identity; an idempotent import
 -- or repeated reads cannot keep creating artificial revisions.
 FOR e IN SELECT * FROM public.cw_review_entries WHERE tenant_id=t AND subject_id=c.subject_id AND indicator_key=c.indicator_key LOOP
  PERFORM public._review_store(t,e.source,public._review_facts(t,e.source),gen_random_uuid());
 END LOOP;
 SET LOCAL ROLE authenticated;
 answer:=public.scheduled_reviews(t,'','independent_minutes','',100);
 RESET ROLE;
 IF EXISTS(SELECT FROM jsonb_array_elements(answer->'items') x WHERE x->>'subject_id'=c.subject_id::text AND (x->>'needs_refresh')::boolean) THEN RAISE EXCEPTION 'consumed measurement remains stale'; END IF;
 -- Historical event/attempt mutation is forbidden even for the scheduler owner.
 BEGIN UPDATE public.cw_review_events SET revision=revision; RAISE EXCEPTION 'immutable event updated'; EXCEPTION WHEN SQLSTATE '42501' THEN NULL; END;
 BEGIN DELETE FROM public.cw_review_attempts; RAISE EXCEPTION 'immutable attempt deleted'; EXCEPTION WHEN SQLSTATE '42501' THEN NULL; END;
END $test$;
ROLLBACK;
''')
print('PASS temporal probes (rolled back SQL roles/claims): future/past C04 deadline, pinned configuration guard, new CSV measurement, stale snapshot detection, immutable events/attempts. These probes do not substitute for real Auth tests above.')
