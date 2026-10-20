"""Logical backup, independent PostgreSQL17 restore and abrupt service recovery. Synthetic stack ONLY."""
from pathlib import Path
exec(Path('e2e/operational-cycles.py').read_text().split('# Previous SQL/security suites')[0])
import hashlib,sys
source=os.environ.get('PG_CONTAINER','cw-mvp-db');info=json.loads(subprocess.check_output(['docker','inspect',source]))[0]
assert info['Config']['Image']=='postgres:17'
assert source=='cw-mvp-db' if os.environ.get('CW_LOCAL_MVP')=='1' else os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
resources=['cw-recovery-rest','cw-recovery-auth','cw-recovery-db'];private=Path('e2e/private');report={}
for name in resources:assert subprocess.run(['docker','inspect',name],capture_output=True).returncode!=0,'Refuse to replace existing '+name
manifest_sql=r"""
SELECT jsonb_build_object(
 'tables',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'owner',pg_get_userbyid(c.relowner),'acl',(SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type,a.is_grantable) ORDER BY pg_get_userbyid(a.grantor),CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END,a.privilege_type) FROM aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a),'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity) ORDER BY n.nspname,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','auth') AND c.relkind='r'),
 'policies',(SELECT jsonb_agg(to_jsonb(x) ORDER BY schemaname,tablename,policyname) FROM pg_policies x WHERE schemaname IN ('public','auth')),
 'functions',(SELECT jsonb_agg(jsonb_build_object('name',p.oid::regprocedure::text,'owner',pg_get_userbyid(p.proowner),'acl',p.proacl::text,'def',pg_get_functiondef(p.oid)) ORDER BY p.oid::regprocedure::text) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('public','auth') AND p.prokind='f'),
 'triggers',(SELECT jsonb_agg(pg_get_triggerdef(t.oid) ORDER BY n.nspname,c.relname,t.tgname) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname IN ('public','auth')),
 'constraints',(SELECT jsonb_agg(jsonb_build_array(n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid)) ORDER BY n.nspname,c.relname,k.conname) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','auth')),
 'indexes',(SELECT jsonb_agg(to_jsonb(x) ORDER BY schemaname,indexname) FROM pg_indexes x WHERE schemaname IN ('public','auth')),
 'roles',(SELECT jsonb_agg(jsonb_build_array(rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolcanlogin,rolreplication,rolbypassrls,rolconnlimit) ORDER BY rolname) FROM pg_roles),
 'role_members',(SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(roleid),pg_get_userbyid(member),admin_option,inherit_option,set_option) ORDER BY pg_get_userbyid(roleid),pg_get_userbyid(member)) FROM pg_auth_members)
)::text;
"""
def run(args,**kw):return subprocess.run(args,check=True,**kw)
def db(container,statement):
 r=subprocess.run(['docker','exec','-i',container,'psql','-X','-qAt','-U','postgres','-d','cw_e2e','-v','ON_ERROR_STOP=1'],input=statement,text=True,capture_output=True);assert r.returncode==0,r.stderr[:500];return r.stdout.strip()
def catalog(container):return json.loads(db(container,manifest_sql))
def data(container):
 tables=db(container,"SELECT quote_ident(schemaname)||'.'||quote_ident(tablename) FROM pg_tables WHERE schemaname IN ('public','auth') ORDER BY schemaname,tablename").splitlines();result={}
 for table in tables:
  # Hash per row then aggregate, bounding the largest aggregate on the 100k-row observation/audit tables.
  result[table]=db(container,"SELECT count(*)||':'||md5(coalesce(string_agg(h,',' ORDER BY h),'')) FROM (SELECT md5(to_jsonb(x)::text) h FROM "+table+' x)r')
 seqs=db(container,"SELECT quote_ident(schemaname)||'.'||quote_ident(sequencename) FROM pg_sequences WHERE schemaname IN ('public','auth') ORDER BY 1").splitlines()
 for seq in seqs:result[seq]=db(container,'SELECT last_value::text||\':\'||is_called FROM '+seq)
 return result
try:
 start=time.monotonic();before=catalog(source);rows=data(source)
 dump=private/'recovery.dump';globals_file=private/'recovery-globals.sql'
 with dump.open('wb') as out:run(['docker','exec',source,'pg_dump','-U','postgres','-d','cw_e2e','-Fc','--compress=6'],stdout=out,stderr=subprocess.PIPE)
 dump.chmod(0o600)
 roles=subprocess.check_output(['docker','exec',source,'pg_dumpall','-U','postgres','--globals-only','--no-role-passwords'],text=True)
 globals_file.write_text('\n'.join(line for line in roles.splitlines() if line.strip()!='CREATE ROLE postgres;'));globals_file.chmod(0o600)
 report.update(backup_seconds=round(time.monotonic()-start,3),backup_bytes=dump.stat().st_size,backup_sha256=hashlib.sha256(dump.read_bytes()).hexdigest(),tables_and_sequences=len(rows))
 # The wrapper keeps tmpfs mounted while the PostgreSQL process itself crashes/restarts.
 run(['docker','run','-d','--name','cw-recovery-db','--label','centerway.disposable=true','--network','cw-e2e','--tmpfs','/var/lib/postgresql/data','-e','POSTGRES_DB=cw_e2e','-e','POSTGRES_HOST_AUTH_METHOD=trust','--entrypoint','/bin/bash','postgres:17','-c','while true; do /usr/local/bin/docker-entrypoint.sh postgres; sleep 1; done'],stdout=subprocess.DEVNULL)
 def ready():
  for _ in range(45):
   if subprocess.run(['docker','exec','cw-recovery-db','pg_isready','-U','postgres','-d','cw_e2e'],capture_output=True).returncode==0:return
   time.sleep(1)
  raise AssertionError('Recovery PostgreSQL did not become ready')
 ready();start=time.monotonic()
 db('cw-recovery-db',globals_file.read_text())
 with dump.open('rb') as inp:run(['docker','exec','-i','cw-recovery-db','pg_restore','-U','postgres','-d','cw_e2e','--exit-on-error','--single-transaction'],stdin=inp,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 assert catalog('cw-recovery-db')==before,'Restored functions/roles/owners/grants/RLS/policies/triggers/constraints/indexes differ'
 assert data('cw-recovery-db')==rows,'Restored data/history/sequences differ'
 report['restore_and_verify_seconds']=round(time.monotonic()-start,3)
 # Prove actual Auth and REST authorization on the independent restored cluster, not just owner counts.
 auth=(private/'auth.env').read_text().replace('@db:5432/','@cw-recovery-db:5432/');rest_env=(private/'rest.env').read_text().replace('@db:5432/','@cw-recovery-db:5432/')
 for name,body in [('recovery-auth.env',auth),('recovery-rest.env',rest_env)]:p=private/name;p.write_text(body);p.chmod(0o600)
 run(['docker','run','-d','--name','cw-recovery-auth','--label','centerway.disposable=true','--network','cw-e2e','-p','127.0.0.1:9998:9999','--env-file',str((private/'recovery-auth.env').resolve()),'supabase/gotrue:v2.177.0'],stdout=subprocess.DEVNULL)
 run(['docker','run','-d','--name','cw-recovery-rest','--label','centerway.disposable=true','--network','cw-e2e','-p','127.0.0.1:54323:3000','--env-file',str((private/'recovery-rest.env').resolve()),'postgrest/postgrest:v12.2.3'],stdout=subprocess.DEVNULL)
 def http(port,path,body,token):
  request=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','apikey':cfg['anon'],'Authorization':'Bearer '+token})
  try:
   with urllib.request.urlopen(request,timeout=15) as r:return r.status,json.loads(r.read() or 'null')
  except urllib.error.HTTPError as r:return r.code,json.load(r)
 def signin(role):
  for _ in range(35):
   try:s,r=http(9998,'/token?grant_type=password',{'email':users[role]['email'],'password':users[role]['password']},cfg['anon'])
   except (urllib.error.URLError,TimeoutError):time.sleep(1);continue
   if s==200:assert r['user']['id']==users[role]['id'] and r['user']['email_confirmed_at'];return r['access_token']
   time.sleep(1)
  raise AssertionError('Restored Auth password grant failed')
 token=signin('admin');foreign=signin('ownerB');tenant=atlas['tenant']
 for _ in range(35):
  try:s,r=http(54323,'/rpc/operational_onboarding',{'_tenant_id':tenant},token)
  except (urllib.error.URLError,TimeoutError):time.sleep(1);continue
  if s==200:break
  time.sleep(1)
 assert s==200 and r['tenant_id']==tenant
 assert http(54323,'/rpc/operational_onboarding',{'_tenant_id':tenant},foreign)[0]==403
 # Quiesce clients before the comparison snapshot: Auth can legitimately write
 # sessions between fingerprinting and the crash, which is not lost data.
 run(['docker','stop','cw-recovery-auth','cw-recovery-rest'],stdout=subprocess.DEVNULL)
 restored_data=data('cw-recovery-db');restored_catalog=catalog('cw-recovery-db')
 # An abrupt PostgreSQL immediate stop produces WAL recovery, preserving committed product data.
 started=time.monotonic();run(['docker','exec','--user','postgres','cw-recovery-db','pg_ctl','-D','/var/lib/postgresql/data','stop','-m','immediate','-w'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 ready();assert catalog('cw-recovery-db')==restored_catalog,'Crash changed catalog/security'
 recovered=data('cw-recovery-db')
 sequences=json.loads(db('cw-recovery-db',"SELECT coalesce(jsonb_object_agg(quote_ident(schemaname)||'.'||quote_ident(sequencename),jsonb_build_object('increment',increment_by,'cycle',cycle)),'{}') FROM pg_sequences WHERE schemaname IN ('public','auth')"))
 assert {k:v for k,v in recovered.items() if k not in sequences}=={k:v for k,v in restored_data.items() if k not in sequences},'Crash lost committed rows/history'
 gaps={}
 for name,definition in sequences.items():
  old,old_called=restored_data[name].split(':');new,new_called=recovered[name].split(':')
  # PostgreSQL pre-logs sequence reservations in WAL. Crash recovery may skip
  # unused numbers, but must not move backwards or reuse committed identities.
  assert not definition['cycle'],'Cyclic sequences need an explicit identity recovery contract'
  assert (int(new)-int(old))*definition['increment']>=0,(name,'sequence moved backwards')
  assert old_called!='true' or new_called=='true',(name,'sequence would reuse its last identity')
  if new!=old:gaps[name]=int(new)-int(old)
 report['sequence_wal_reservation_gaps']=gaps
 assert 'automatic recovery' in subprocess.check_output(['docker','logs','cw-recovery-db'],stderr=subprocess.STDOUT,text=True)
 report['abrupt_postgres_recovery_seconds']=round(time.monotonic()-started,3)
 run(['docker','start','cw-recovery-auth','cw-recovery-rest'],stdout=subprocess.DEVNULL)
 token=signin('admin');assert http(54323,'/rpc/operational_onboarding',{'_tenant_id':tenant},token)[0]==200
 report.update(status='passed',auth='real restored GoTrue password grant',rls='restored PostgREST allows member, rejects foreign user',scope='all public/auth rows, sequences, role memberships, owners, grants, policies, functions, constraints, indexes and non-internal triggers',limits=['Disposable PostgreSQL17 logical snapshot; not Supabase hosted backup/PITR verification.','JWT/provider secrets and external storage/configuration are not supplied by pg_dump; ephemeral test env copied privately.','Cluster roles exported without passwords; production connection credentials require a separate secure recovery procedure.'])
 Path('e2e/logs/reliability-restore.json').write_text(json.dumps(report,indent=2));print('PASS backup/restore:',json.dumps(report),flush=True)
finally:
 for name in resources:
  r=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
  if r.returncode==0:
   assert json.loads(r.stdout)[0]['Config'].get('Labels',{}).get('centerway.disposable')=='true'
   subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for name in ['recovery.dump','recovery-globals.sql','recovery-auth.env','recovery-rest.env']:(private/name).unlink(missing_ok=True)
