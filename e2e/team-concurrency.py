"""Real GoTrue/PostgREST requests, distinct PostgreSQL transactions, isolated synthetic DB only."""
import concurrent.futures as pool
from datetime import datetime,timezone,timedelta
import json,os,subprocess,time,urllib.request,urllib.error,uuid
from pathlib import Path
if os.environ.get('CW_LOCAL_MVP')=='1':
 d=json.loads(subprocess.check_output(['docker','inspect','cw-mvp-db']))[0]
 assert d['Config']['Image']=='postgres:17' and d['Config']['Labels']['centerway.disposable']=='mvp'
 assert '/var/lib/postgresql/data' in d['HostConfig']['Tmpfs'] and not d.get('Mounts')
else:
 assert os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
assert os.environ.get('PGHOST')=='127.0.0.1' and os.environ.get('PGDATABASE')=='cw_e2e'
cfg=json.loads(Path('e2e/private/public.json').read_text());assert cfg['url']=='http://127.0.0.1:54321'
users=json.loads(Path('e2e/private/team-users.json').read_text())
env={k:v for k,v in os.environ.items() if k not in ('PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGHOSTADDR','PGOPTIONS')};env['PGPASSFILE']='/dev/null'
psql=['psql','-X','-qAt','-h','127.0.0.1','-p','5432','-U','postgres','-d','cw_e2e','-v','ON_ERROR_STOP=1']
def sql(statement):
 r=subprocess.run(psql,input=statement,text=True,capture_output=True,env=env,check=True);return r.stdout.strip()
def literal(v): return "'"+str(v).replace("'","''")+"'"
def http(path,user,body):
 token=users[user]['token'] if user else cfg['anon']
 req=urllib.request.Request(cfg['url']+path,data=json.dumps(body).encode(),headers={'apikey':cfg['anon'],'Authorization':'Bearer '+token,'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=20) as r:
   body=r.read();return r.status,json.loads(body) if body else None
 except urllib.error.HTTPError as r:return r.code,json.load(r)
def rpc(name,user,body):return http('/rest/v1/rpc/'+name,user,body)
for name,u in users.items():
 status,result=http('/auth/v1/token?grant_type=password',None,{'email':u['email'],'password':u['password']});assert status==200;u['token']=result['access_token']
tables=sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('tenants','memberships','audit_log','tenant_invitations') ORDER BY tablename;").splitlines()
def fingerprint():
 return [sql('SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),\'[]\')::text,\'UTF8\')),\'hex\') FROM public."'+t+'" x;') for t in tables]
before=fingerprint()
status,t=rpc('create_tenant','admin',{'_name':'[SINTÉTICO] Concurrent access probes','_subject_unit_type':'organization'});assert status==200
assert rpc('add_tenant_member','admin',{'_tenant_id':t,'_user_id':users['secondAdmin']['id'],'_role':'admin'})[0]==200
expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
def invite(recipient,role='operator'):
 status,v=rpc('create_tenant_invitation','admin',{'_tenant_id':t,'_email':users[recipient]['email'],'_role':role,'_expires_at':expiry,'_operation_id':str(uuid.uuid4())});assert status==200;return v
v=invite('invitee');ops=[str(uuid.uuid4()),str(uuid.uuid4())]
with pool.ThreadPoolExecutor() as executor:
 results=list(executor.map(lambda op:rpc('accept_tenant_invitation','invitee',{'_token':v['token'],'_operation_id':op}),ops))
assert sorted(r[0] for r in results)==[200,400]
winner=ops[next(i for i,r in enumerate(results) if r[0]==200)]
assert sql(f"SELECT count(*) FROM public.memberships WHERE tenant_id={literal(t)} AND user_id={literal(users['invitee']['id'])};")=='1'
assert rpc('accept_tenant_invitation','invitee',{'_token':v['token'],'_operation_id':winner})[0]==200
assert rpc('remove_tenant_member','admin',{'_tenant_id':t,'_user_id':users['invitee']['id']})[0] in (200,204)
assert rpc('accept_tenant_invitation','invitee',{'_token':v['token'],'_operation_id':winner})[0]==400
# Verify actual issued JWT cannot substitute for current verified auth.users email state.
v=invite('unverified');uid=users['unverified']['id'];confirmed=sql(f'SELECT email_confirmed_at FROM auth.users WHERE id={literal(uid)};')
try:
 sql(f'UPDATE auth.users SET email_confirmed_at=NULL WHERE id={literal(uid)};')
 assert rpc('inspect_tenant_invitation','unverified',{'_token':v['token']})[0]==403
 assert rpc('accept_tenant_invitation','unverified',{'_token':v['token'],'_operation_id':str(uuid.uuid4())})[0]==403
finally:sql(f'UPDATE auth.users SET email_confirmed_at={literal(confirmed)} WHERE id={literal(uid)};')
# Hold the tenant row in another PostgreSQL session; prove the stale-admin HTTP call actually waits.
lock=subprocess.Popen(psql,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,bufsize=1)
lock.stdin.write(f"BEGIN; SELECT id FROM public.tenants WHERE id={literal(t)} FOR UPDATE; SELECT 'TEAM_LOCK_HELD';\n");lock.stdin.flush()
while True:
 line=lock.stdout.readline()
 assert line,'lock process ended before marker'
 if line.strip()=='TEAM_LOCK_HELD':break
with pool.ThreadPoolExecutor() as executor:
 pending=executor.submit(rpc,'create_tenant_invitation','admin',{'_tenant_id':t,'_email':users['invitee']['email'],'_role':'admin','_expires_at':expiry,'_operation_id':str(uuid.uuid4())})
 deadline=time.monotonic()+10
 while sql("SELECT EXISTS(SELECT FROM pg_stat_activity WHERE datname='cw_e2e' AND wait_event_type='Lock' AND query LIKE '%create_tenant_invitation%');")!='t':
  assert time.monotonic()<deadline,'HTTP admin operation never waited on the shared tenant lock'
  time.sleep(.05)
 claims=json.dumps({'role':'authenticated','sub':users['secondAdmin']['id']})
 lock.stdin.write(f"SELECT set_config('request.jwt.claims',{literal(claims)},true); SET LOCAL ROLE authenticated; SELECT public.set_member_role({literal(t)},{literal(users['admin']['id'])},'operator'); COMMIT;\n");lock.stdin.close()
 assert lock.wait(timeout=10)==0
 assert pending.result()[0]==403,'revoked administrator committed after waiting'
assert rpc('set_member_role','secondAdmin',{'_tenant_id':t,'_user_id':users['admin']['id'],'_role':'admin'})[0] in (200,204)
# Concurrent administrators removing each other: exactly one surviving administrator.
with pool.ThreadPoolExecutor() as executor:
 a=executor.submit(rpc,'remove_tenant_member','admin',{'_tenant_id':t,'_user_id':users['secondAdmin']['id']})
 b=executor.submit(rpc,'remove_tenant_member','secondAdmin',{'_tenant_id':t,'_user_id':users['admin']['id']})
 assert sorted([a.result()[0],b.result()[0]])==[204,403]
assert sql(f"SELECT count(*) FROM public.memberships WHERE tenant_id={literal(t)} AND role='admin';")=='1'
assert before==fingerprint(),'access management changed C01-C10 data'
print('Real HTTP/PostgreSQL concurrency passed: single-use accept, safe replay after removal, unverified active JWT rejected, locked/revoked admin denied, one last admin preserved, C01-C10 unchanged.')
