"""Connection loss, rollback on termination, replay and stateless API restart. Synthetic only."""
from pathlib import Path
exec(Path('e2e/operational-cycles.py').read_text().split('# Previous SQL/security suites')[0])
import threading,http.server,socket,ssl
report={};state=json.loads(Path('e2e/private/reliability.json').read_text());company=state['companies'][0];t=company['tenant'];subject=company['subject'];case=company['case'];profile=company['profile']
def checked(name,args,role='admin'):
 s,r=rpc(name,args,role);assert s in (200,204),(name,s,r);return r
def core():return sql("SELECT md5(jsonb_build_array((SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_operational_cases x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_operational_events x))::text)")
initial=core()
# Force disconnect after a valid C01 import has written inside its transaction, before COMMIT.
row={'line':1,'subject_external_ref':'load-0','indicator_key':'cycle_minutes','observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'value_numeric':51,'unit':'min','idempotency_key':newid()}
body={'_tenant_id':t,'_expected_profile_id':profile,'_source':'synthetic-load','_coverage_start':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=1)).isoformat(),'_coverage_end':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=1)).isoformat(),'_coverage_declared':True,'_file_name':'[SINTÉTICO] interrupted.csv','_rows':[row]}
# Import validation forbids future coverage end? Use current instant after observed_at.
body['_coverage_end']=dt.datetime.now(dt.timezone.utc).isoformat()
def terminate_transaction(statement):
 p=subprocess.Popen(['psql','-X','-qAt','-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env,bufsize=1)
 p.stdin.write('BEGIN; SELECT pg_backend_pid();\n');p.stdin.flush();pid=int(p.stdout.readline())
 p.stdin.write("SELECT set_config('request.jwt.claims',"+lit(json.dumps({'role':'authenticated','sub':users['admin']['id']})) +",true); SET ROLE authenticated; "+statement+"; SELECT 'CW_UNCOMMITTED';\n");p.stdin.flush()
 for line in p.stdout:
  if line.strip()=='CW_UNCOMMITTED':break
 else:raise AssertionError('Transaction did not reach fault barrier')
 assert sql('SELECT pg_terminate_backend('+str(pid)+')')=='t'
 p.stdin.close();p.wait(timeout=20)
 assert sql('SELECT NOT EXISTS(SELECT FROM pg_stat_activity WHERE pid='+str(pid)+')')=='t'  # An idle psql can exit 0 on EOF despite backend termination.
before=sql('SELECT count(*) FROM observations');audit=sql('SELECT count(*) FROM audit_log')
args=','.join([lit(t),lit(profile),lit(body['_source']),lit(body['_coverage_start']),lit(body['_coverage_end']),'true',lit(body['_file_name']),lit(json.dumps(body['_rows']))])
terminate_transaction('SELECT public.import_observations('+args+')')
assert sql('SELECT count(*) FROM observations')==before and sql('SELECT count(*) FROM audit_log')==audit
r=checked('import_observations',body);assert r['status']=='completed' and r['inserted']==1
r=checked('import_observations',body);assert r['inserted']==0 and r['duplicates']==1
report['uncommitted_import_disconnect']='rolled back observations/batch/audit; replay persisted exactly one observation'
# Lost acknowledgement: real HTTP commits, a loopback proxy drops its response, same keys safely replay.
row={**row,'idempotency_key':newid()};body={**body,'_rows':[row]}
class LostAck(http.server.BaseHTTPRequestHandler):
 def do_POST(self):
  length=int(self.headers['Content-Length']);data=self.rfile.read(length)
  request=urllib.request.Request(cfg['url']+'/rest/v1/rpc/import_observations',data=data,headers={'Content-Type':'application/json','apikey':cfg['anon'],'Authorization':'Bearer '+users['admin']['token']})
  with urllib.request.urlopen(request,timeout=60) as r:assert json.load(r)['status']=='completed'
  self.close_connection=True;self.connection.shutdown(socket.SHUT_RDWR);self.connection.close()
 def log_message(self,*args):pass
server=http.server.HTTPServer(('127.0.0.1',0),LostAck);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port),data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:urllib.request.urlopen(request,timeout=60);raise AssertionError('Lost acknowledgement unexpectedly arrived')
 except (urllib.error.URLError,ConnectionError, __import__('http.client',fromlist=['RemoteDisconnected']).RemoteDisconnected):pass
 r=checked('import_observations',body);assert r['inserted']==0 and r['duplicates']==1
finally:server.shutdown();server.server_close();thread.join(timeout=5)
report['committed_import_lost_ack']='real HTTP commit followed by transport disconnect; same idempotency keys returned duplicates, no second observation'
assert core()==initial,'C01 import/replay unexpectedly changed Core history'
# Human Core command with a real Auth token; terminate its HTTP backend inside the event trigger.
version=get('cw_operational_cases?id=eq.'+case)[0]['version']
command={'_tenant_id':t,'_case_id':case,'_expected_version':version,'_operation_id':newid(),'_command':'start_cycle','_payload':{'reason':'[SINTÉTICO] Continuidade documentada após indisponibilidade','reference':'urn:recovery:continuation'}}
sql("CREATE FUNCTION public.cw_recovery_barrier() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.case_id="+lit(case)+"::uuid AND NEW.operation_id="+lit(command['_operation_id'])+"::uuid THEN PERFORM pg_advisory_xact_lock(918273645); END IF;RETURN NEW;END $$; CREATE TRIGGER cw_recovery_barrier AFTER INSERT ON cw_operational_events FOR EACH ROW EXECUTE FUNCTION public.cw_recovery_barrier();")
# Hold the barrier in a separate connection; find only the blocked transaction, never its headers/SQL.
lock=subprocess.Popen(['psql','-X','-qAt','-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env,bufsize=1)
lock.stdin.write("BEGIN; SELECT pg_advisory_xact_lock(918273645); SELECT 'LOCKED';\n");lock.stdin.flush()
for line in lock.stdout:
 if line.strip()=='LOCKED':break
before=core()
try:
 with concurrent.futures.ThreadPoolExecutor(1) as pool:
  future=pool.submit(rpc,'command_operational_case',command)
  blocked=None
  for _ in range(100):
   candidate=sql("SELECT pid FROM pg_locks WHERE locktype='advisory' AND NOT granted AND objid=918273645")
   if candidate:blocked=int(candidate);break
   time.sleep(.05)
  assert blocked,'HTTP Core operation did not reach the transaction barrier'
  assert sql('SELECT pg_terminate_backend('+str(blocked)+')')=='t'
  try:answer=future.result(timeout=20);assert answer[0]>=400,answer
  except (urllib.error.URLError,ConnectionError):pass
 assert core()==before,'Interrupted Core command committed a partial decision/cycle/event'
finally:
 lock.stdin.write('ROLLBACK;\n');lock.stdin.close();lock.wait(timeout=10)
 sql('DROP TRIGGER cw_recovery_barrier ON cw_operational_events; DROP FUNCTION public.cw_recovery_barrier();')
result=checked('command_operational_case',command);assert checked('command_operational_case',command)==result
assert get('cw_operational_cases?id=eq.'+case)[0]['version']==version+1
assert sql('SELECT count(*) FROM cw_operational_cycles WHERE case_id='+lit(case))=='3'
report['core_backend_terminated']='real authenticated HTTP transaction rolled back completely; replay started one new cycle only'
# Create a real current-cycle plan requiring authorization; its job must survive interruption.
proof=get('observations?select=id&tenant_id=eq.'+t+'&subject_id=eq.'+subject+'&limit=1')[0]['id']
for name,payload in [('investigate',{'status':'confirmed','finding':'[SINTÉTICO] Revisão humana para teste de retoma','reference':'urn:recovery:finding','observation_ids':[proof]}),('plan',{'action':'[SINTÉTICO] Intervenção apenas proposta','rationale':'Teste de recuperação de outbox','success_conditions':'Prova posterior e revisão humana','limitations':'Não comprova valor','reversal':'Revisão humana','reference':'urn:recovery:plan','observation_seconds':1})]:
 current=get('cw_operational_cases?id=eq.'+case)[0]
 plan=checked('command_operational_case',{'_tenant_id':t,'_case_id':case,'_expected_version':current['version'],'_operation_id':newid(),'_command':name,'_payload':payload},'operator')
assert sql("SELECT count(*) FROM cw_notification_jobs WHERE source_id="+lit(plan)+" AND status='pending'")=='1'
# Notification preparation interrupted before commit leaves its outbox recoverable.
before_jobs=sql("SELECT md5(jsonb_build_array((SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_notification_jobs x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_notifications x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_notification_attempts x))::text)")
terminate_transaction('SELECT public.prepare_operational_notifications('+lit(t)+')')
after_jobs=sql("SELECT md5(jsonb_build_array((SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_notification_jobs x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_notifications x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_notification_attempts x))::text)")
assert before_jobs==after_jobs
assert checked('prepare_operational_notifications',{'_tenant_id':t})['processed']>=1
# Each call processes at most 25 DISTINCT due jobs. A backlog may legitimately
# create more notifications on the next call; it is not a duplicate/replay.
for _ in range(100):
 if checked('prepare_operational_notifications',{'_tenant_id':t})['processed']==0:break
else:raise AssertionError('Bounded notification backlog did not drain')
assert sql("SELECT status||':'||attempts FROM cw_notification_jobs WHERE source_kind='core' AND source_id="+lit(plan))=='completed:1','Interrupted job did not recover exactly once'
assert sql("SELECT count(*) FROM cw_notifications WHERE source_kind='core' AND source_id="+lit(plan)+" AND kind='authorization_needed' AND recipient_id="+lit(users['admin']['id']))=='1'
assert sql("SELECT count(*) FROM cw_notification_jobs WHERE tenant_id="+lit(t)+" AND status IN ('pending','failed')")=='0'
notifications=sql("SELECT md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]'::jsonb)::text) FROM cw_notifications x")
for _ in range(3):assert checked('prepare_operational_notifications',{'_tenant_id':t})['processed']==0
assert sql("SELECT md5(coalesce(jsonb_agg(to_jsonb(x) ORDER BY id),'[]'::jsonb)::text) FROM cw_notifications x")==notifications
report['notification_worker_disconnect']='jobs, notifications and attempts rolled back atomically; retry remains deduplicated'
# Restore reachability after an actual stateless PostgREST service restart.
rest_info=json.loads(subprocess.check_output(['docker','inspect','cw-rest']))[0];assert rest_info['Config']['Labels']['centerway.disposable']=='true'
run_before=core();subprocess.run(['docker','restart','cw-rest'],check=True,stdout=subprocess.DEVNULL)
for _ in range(40):
 try:
  s,r=rpc('operational_onboarding',{'_tenant_id':t})
  if s==200:break
 except (urllib.error.URLError,ConnectionError):pass
 time.sleep(.5)
else:raise AssertionError('REST did not recover')
assert core()==run_before
report['postgrest_restart']='existing real JWT works after service restart; Core history unchanged'
report['automatic_case_actions']='none: only explicitly requested synthetic human commands changed the selected case; ingestion/reads/worker never changed other cases'
Path('e2e/logs/reliability-recovery.json').write_text(json.dumps(report,indent=2));print('PASS recovery:',json.dumps(report),flush=True)
