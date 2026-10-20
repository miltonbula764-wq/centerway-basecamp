"""Real synthetic GoTrue/PostgREST + disposable PostgreSQL: responsibilities and inbox."""
# Reuse the existing real-auth test harness, not its journey/mutations.
from pathlib import Path
exec(Path('e2e/operational-cycles.py').read_text().split('# Previous SQL/security suites')[0])
f=json.loads(Path('e2e/cycle-fixtures.json').read_text());t=f['tenant'];case=f['case'];operator=users['operator']['id'];admin=users['admin']['id'];viewer=users['viewer']['id']
def ok(name,args,role='admin'):
 s,r=rpc(name,args,role);assert s in (200,204),(name,s,r);return r
base={'_tenant_id':t,'_case_id':case}
def responsibility():return ok('case_responsibility',base)
def inbox(role='operator',**kw):return ok('notification_inbox',{'_tenant_id':t,**kw},role)
def assign(target,revision=None,operation=None):return {**base,'_assignee_id':target,'_reason':'[SINTÉTICO] Decisão humana documentada','_reference':'urn:responsibilities:test','_expected_revision':responsibility()['current']['revision'] if revision is None and responsibility()['current'] else (revision or 0),'_operation_id':operation or newid()}
def work(role='operator',**kw):return ok('my_operational_work',{'_tenant_id':t,**kw},role)
def flush():return ok('prepare_operational_notifications',{'_tenant_id':t})
# Fingerprint operational history, independent of assignment/audit/notification tables.
tables=sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND (tablename LIKE 'cw_operational_%' OR tablename IN ('cw_cases','cw_case_events','c04_configurations','c04_evaluations','observations')) ORDER BY tablename").splitlines()
def fingerprint():return [sql('SELECT md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),\'[]\')::text) FROM public.'+table+' x') for table in tables]
before=fingerprint();args=assign(operator,0)
for role in ['operator','viewer','ownerB',None]:assert rpc('assign_operational_case',args,role)[0] in (401,403)
for target in [users['ownerB']['id'],viewer]:assert rpc('assign_operational_case',{**args,'_assignee_id':target})[0]==400
assert rpc('assign_operational_case',{**args,'_reason':''})[0]==400
with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:rpc('assign_operational_case',args),range(4)))
assert all(s==200 and r==results[0][1] for s,r in results),results
assert responsibility()['valid'] and responsibility()['current']['revision']==1
assert any(i['case_id']==case for i in work()['items'])
a=inbox();assert len(a['items'])==1 and a['items'][0]['kind']=='case_assigned';notification=a['items'][0]['id'];assert a['unread_count']==1
assert not inbox('viewer')['items'] and not inbox('admin')['items']
assert get('cw_notifications?select=id&tenant_id=eq.'+t,'viewer')==[]
assert rpc('mark_notification_read',{'_tenant_id':t,'_notification_id':notification},'admin')[0]==403
assert rpc('notification_inbox',{'_tenant_id':t},'ownerB')[0]==403
assert get('cw_notifications?select=id&tenant_id=eq.'+t,'ownerB')==[]
for _ in range(2):ok('mark_notification_read',{'_tenant_id':t,'_notification_id':notification},'operator')
assert inbox()['unread_count']==0 and inbox()['items'][0]['is_read'] and inbox(_unread_only=True)['items']==[]
assert rpc('assign_operational_case',{**args,'_reason':'conflict'})[0]==400
# Distinct competing revision claims cannot overwrite each other.
competing=[assign(admin,1),assign(None,1)]
with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda a:rpc('assign_operational_case',a),competing))
assert sorted(s for s,r in results)==[200,409],results
assert responsibility()['current']['revision']==2 and not work()['items']
assert any(n['kind']=='responsibility_changed' for n in inbox()['items'])
ok('assign_operational_case',assign(operator));revision=responsibility()['current']['revision']
# Actual membership changes invalidate operational access without erasing history.
ok('set_member_role',{'_tenant_id':t,'_user_id':operator,'_role':'viewer'})
assert not responsibility()['valid'] and work()['items']==[] and inbox()['items']==[n for n in inbox()['items'] if n['kind']=='responsibility_changed']
assert rpc('prepare_operational_notifications',{'_tenant_id':t},'operator')[0]==403
ok('set_member_role',{'_tenant_id':t,'_user_id':operator,'_role':'operator'})
ok('remove_tenant_member',{'_tenant_id':t,'_user_id':operator})
assert rpc('notification_inbox',{'_tenant_id':t},'operator')[0]==403
ok('add_tenant_member',{'_tenant_id':t,'_user_id':operator,'_role':'operator'})
assert not responsibility()['valid'] and work()['items']==[] and inbox()['items']==[]
ok('assign_operational_case',assign(operator));assert responsibility()['valid'] and responsibility()['current']['revision']==revision+1 and inbox()['unread_count']==1
# Retry queue: failure details stay private, completed deliveries are never duplicated.
# Enqueue an actual failed monitoring attempt through the existing scheduler failure path.
sql("CREATE FUNCTION public.cw_notify_test_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic private detail' USING ERRCODE='P0099'; END $$; CREATE TRIGGER cw_notify_test_fault BEFORE INSERT ON public.cw_notifications FOR EACH ROW EXECUTE FUNCTION public.cw_notify_test_fault();")
# A genuine monitoring failure (bounded transaction) creates the immutable failure event.
sql("CREATE FUNCTION public.cw_scan_test_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic scan detail' USING ERRCODE='P0098'; END $$; CREATE TRIGGER cw_scan_test_fault BEFORE UPDATE ON public.cw_review_entries FOR EACH ROW EXECUTE FUNCTION public.cw_scan_test_fault();")
try:
 attempt=ok('prepare_scheduled_reviews',{'_tenant_id':t,'_operation_id':newid()});assert attempt['status']=='failed'
 flush()
 assert sql("SELECT count(*) FROM cw_notification_jobs WHERE tenant_id="+lit(t)+" AND source_kind='attempt' AND status='failed'")=='1'
 assert 'synthetic private detail' not in json.dumps(inbox('admin'))
finally:
 sql('DROP TRIGGER cw_notify_test_fault ON public.cw_notifications; DROP FUNCTION public.cw_notify_test_fault(); DROP TRIGGER cw_scan_test_fault ON public.cw_review_entries; DROP FUNCTION public.cw_scan_test_fault();')
# Only the technical retry timestamp is made due; no case clock or business date is changed.
sql("UPDATE cw_notification_jobs SET next_try_at=clock_timestamp() WHERE tenant_id="+lit(t)+" AND status='failed'")
with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:rpc('prepare_operational_notifications',{'_tenant_id':t}),range(4)))
assert all(s==200 for s,r in results),results
assert len([n for n in inbox('admin')['items'] if n['kind']=='operational_failure'])==1
count=sql('SELECT count(*) FROM cw_notifications');flush();flush();assert sql('SELECT count(*) FROM cw_notifications')==count
assert sql("SELECT count(*) FROM cw_notification_attempts WHERE status='failed' AND error_code='P0099'")!='0'
# Direct writes/private engines are denied, including anonymous users.
for table in ['cw_case_assignments','cw_notifications','cw_notification_reads','cw_notification_jobs','cw_notification_attempts']:
 assert rest('/rest/v1/'+table,{},'admin')[0]==403
for name,args2 in [('_notification_process',{'_tenant':t,'_limit':25}),('_notification_put',{})]:assert rpc(name,args2)[0] in (403,404)
# The dedicated scheduler still works after 0022 without a human impersonation or generic grants.
with concurrent.futures.ThreadPoolExecutor(2) as pool:
 results=list(pool.map(lambda _:sql('SET ROLE centerway_review_scheduler; SELECT public.process_review_schedule(2);'),range(2)))
for result in results:
 for attempt in json.loads(result)['attempts']:
  assert attempt['actor_kind']=='scheduler' and attempt['actor_id'] is None and attempt['status']=='completed'
assert sql("SELECT has_table_privilege('centerway_review_scheduler','public.cw_notifications','SELECT')")=='f'
assert fingerprint()==before,'Assignment/notification processing changed C01-C10'
# SQL tests cover real database roles/claims; independent from real GoTrue above.
for suite,marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS'),('c03','CW_C03_RESULTS')]:
 r=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+suite+'_test.sql'],env=env,text=True,capture_output=True)
 Path('e2e/logs/responsibilities-'+suite+'.log').write_text(r.stdout+r.stderr)
 assert r.returncode==3 and re.search(marker+r' pass=\d+ fail=0(?: |$)',r.stdout+r.stderr),suite
# Owner setup + authenticated SQL roles, entirely rolled back; no fabricated historical clock.
probe={**f,'operator':operator,'admin':admin}
sql("BEGIN; SELECT set_config('cw.responsibility_fixture',"+lit(json.dumps(probe))+",true); SELECT set_config('request.jwt.claims',"+lit(json.dumps({'role':'authenticated','sub':admin}))+",true);"+Path('e2e/responsibilities-review.sql').read_text()+"ROLLBACK;")
Path('e2e/responsibility-fixtures.json').write_text(json.dumps({**f,'operator':operator,'admin':admin}))
print('PASS responsibilities: real verified GoTrue/Auth, tenant RLS, admin-only assignment, immutable revisions, concurrent replay/CAS, no privilege elevation, membership demotion/removal/rejoin, private inbox, read replay, outbox failure/recovery, concurrent processors/dedup, unchanged C01-C10 and SQL regression. No hosted execution.')
