"""Synthetic capacity probe. Requires the labelled disposable stack or GitHub-hosted PostgreSQL17."""
from pathlib import Path
exec(Path('e2e/operational-cycles.py').read_text().split('# Previous SQL/security suites')[0])
import statistics,platform,sys
state_path=Path('e2e/private/reliability.json');report_path=Path('e2e/logs/reliability-scale.json')
report={}
def save():report_path.write_text(json.dumps(report,indent=2))
def checked(name,args,role='admin'):
 s,r=rpc(name,args,role);assert s in (200,204),(name,s,r);return r
def fingerprint():
 scope=','.join(lit(c['tenant']) for c in companies)
 return sql("SELECT md5(jsonb_build_array((SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_operational_cases x WHERE tenant_id IN ("+scope+")),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_operational_events x WHERE tenant_id IN ("+scope+")),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_case_assignments x WHERE tenant_id IN ("+scope+")))::text)")
def hardware():
 info={'architecture':platform.machine(),'logical_cpus':os.cpu_count(),'postgres':sql('SHOW server_version'),'shared_buffers':sql('SHOW shared_buffers'),'max_connections':sql('SHOW max_connections'),'storage':'disposable tmpfs; no production durability/IOPS claim'}
 for file in ['cpu.max','memory.max','memory.peak']:
  p=Path('/sys/fs/cgroup/'+file)
  if p.exists():info[file]=p.read_text().strip()
 return info
if '--seed' in sys.argv:
 started=time.monotonic();template=get('profile_indicators?tenant_id=eq.'+atlas['tenant']+'&profile_id=eq.'+atlas['profile']+'&key=eq.cycle_minutes')[0]
 companies=[];counts={'companies':0,'clients':0,'observations':0};imports=[]
 midnight=dt.datetime.now(dt.timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
 date=lambda n:(midnight+dt.timedelta(days=n)).isoformat()
 for n in range(100):
  tenant=checked('create_tenant',{'_name':'[SINTÉTICO CARGA] SaaS '+str(n),'_subject_unit_type':'organization'})
  profile=checked('create_value_profile_draft',{'_tenant_id':tenant,'_promise':'[SINTÉTICO] Tempo documentado; sem SLA universal'})
  row={k:v for k,v in template.items() if k not in ('id','tenant_id','profile_id','created_at','updated_at')};row.update(tenant_id=tenant,profile_id=profile)
  assert rest('/rest/v1/profile_indicators',row)[0]==201
  checked('approve_value_profile',{'_profile_id':profile})
  total=505 if n==0 else 5
  rows=[{'tenant_id':tenant,'external_ref':'load-'+str(k),'display_name':'[SINTÉTICO] Cliente '+str(k)} for k in range(total)]
  s,subjects=rest('/rest/v1/subjects?select=id,external_ref',rows);assert s==201 and len(subjects)==total
  for offset in range(0,total,10):
   batch=subjects[offset:offset+10];values=[]
   for customer in batch:
    for d in range(1,101):values.append({'line':len(values)+1,'subject_external_ref':customer['external_ref'],'indicator_key':'cycle_minutes','observed_at':date(-d),'value_numeric':50,'unit':'min','idempotency_key':newid()})
   body={'_tenant_id':tenant,'_expected_profile_id':profile,'_source':'synthetic-load','_coverage_start':date(-101),'_coverage_end':date(0),'_coverage_declared':True,'_file_name':'[SINTÉTICO] carga.csv','_rows':values}
   begin=time.monotonic();r=checked('import_observations',body);imports.append((time.monotonic()-begin)*1000);assert r['status']=='completed' and r['inserted']==len(values)
   counts['observations']+=r['inserted']
  subject=subjects[0]['id'];definition={**atlas['definition'],'source':'synthetic-load','observation_start':date(-101),'deadline':date(-1)}
  config=checked('save_c04_configuration',{'_tenant_id':tenant,'_subject_id':subject,'_profile_id':profile,'_indicator_key':'cycle_minutes','_previous_id':None,'_operation_id':newid(),'_definition':definition})
  run=checked('run_deterioration_analysis',{'_tenant_id':tenant,'_subject_id':subject,'_expected_profile_id':profile})
  bundle=checked('build_evidence_bundle',{'_tenant_id':tenant,'_run_id':run['run_id']})
  evaluation=checked('evaluate_c04_configuration',{'_tenant_id':tenant,'_configuration_id':config,'_bundle_id':bundle['bundle_id']})
  company={'tenant':tenant,'profile':profile,'subject':subject,'configuration':config,'bundle':bundle['bundle_id'],'evaluation':evaluation,'clients':total}
  if n<10:
   for role in ['operator','viewer']:checked('add_tenant_member',{'_tenant_id':tenant,'_user_id':users[role]['id'],'_role':role})
  companies.append(company);counts['companies']+=1;counts['clients']+=total
  if n%10==0:print('Synthetic load progress:',counts,flush=True)
 assert counts=={'companies':100,'clients':1000,'observations':100000},counts
 state_path.write_text(json.dumps({'companies':companies}));state_path.chmod(0o600)
 report={'scope':counts,'hardware':hardware(),'seed_seconds':round(time.monotonic()-started,3),'import_ms':{'n':len(imports),'median':round(statistics.median(imports),3),'max':round(max(imports),3)},'limits':['Local HTTP/Auth/PostgreSQL17, cached/synthetic workload, no production capacity guarantee.','100 SaaS: busiest has 505 clients; other 99 have 5 each; 100 observations per client.','Seed uses authorized real Auth/C01 RPCs; no direct observation writes.']};save()
 print('PASS synthetic load seed:',counts,flush=True)
else:
 state=json.loads(state_path.read_text());companies=state['companies'];report=json.loads(report_path.read_text());busy=companies[0];t=busy['tenant']
 # Explicit synthetic human decisions: two cycles per case. Never forge a clock or retroactive execution.
 def cycles(company):
  tenant=company['tenant'];subject=company['subject'];existing=get('cw_operational_cases?tenant_id=eq.'+tenant+'&subject_id=eq.'+subject+'&evaluation_id=eq.'+company['evaluation']);case=existing[0]['id'] if existing else checked('open_operational_case',{'_tenant_id':tenant,'_evaluation_id':company['evaluation'],'_operation_id':newid(),'_definition':{'eligible':True,'configuration_pinned':True,'eligibility_reason':'[SINTÉTICO] Decisão humana do teste','eligibility_ref':'urn:load:opening','opening_criteria':'[SINTÉTICO] Critério específico','closure_criteria':'Prova suficiente posterior ao ciclo','closure_ref':'urn:load:closure'}})
  if not checked('case_responsibility',{'_tenant_id':tenant,'_case_id':case})['current']:checked('assign_operational_case',{'_tenant_id':tenant,'_case_id':case,'_assignee_id':users['operator']['id'],'_expected_revision':0,'_operation_id':newid(),'_reason':'[SINTÉTICO] Responsável humano','_reference':'urn:load:assignment'})
  proof=get('observations?select=id&tenant_id=eq.'+tenant+'&subject_id=eq.'+subject+'&limit=1')[0]['id']
  def command(name,payload,role='admin'):
   current=get('cw_operational_cases?id=eq.'+case)[0]
   return checked('command_operational_case',{'_tenant_id':tenant,'_case_id':case,'_expected_version':current['version'],'_operation_id':newid(),'_command':name,'_payload':payload},role)
  for cycle in range(2):
   h=checked('operational_cycle_history',{'_tenant_id':tenant,'_case_id':case})
   if h['current']['number']>cycle+1:continue
   if h['current']['number']<cycle+1:command('start_cycle',{'reason':'[SINTÉTICO] Continuidade humana documentada','reference':'urn:load:continuation'})
   heads=checked('operational_cycle_history',{'_tenant_id':tenant,'_case_id':case})['heads']
   if 'investigate' not in heads:command('investigate',{'status':'confirmed','finding':'[SINTÉTICO] Facto revisto por pessoa no teste','reference':'urn:load:finding','observation_ids':[proof]},'operator')
   if 'plan' not in heads:command('plan',{'action':'[SINTÉTICO] Ação humana de teste','rationale':'Critério específico do teste','success_conditions':'Objetivo histórico e evidência posterior','limitations':'Não atribui causalidade','reversal':'Revisão humana antes da reversão','reference':'urn:load:plan','observation_seconds':1},'operator')
   if 'approve' not in heads:command('approve',{'valid_until':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),'reason':'[SINTÉTICO] Aprovação independente','reference':'urn:load:approval'})
   if 'record_execution' not in heads:command('record_execution',{'receipt':'[SINTÉTICO] Registo de ação humana; não prova valor','reference':'urn:load:receipt'},'operator')
   time.sleep(1.05)
   if 'observe' not in heads:
    run=checked('run_deterioration_analysis',{'_tenant_id':tenant,'_subject_id':subject,'_expected_profile_id':company['profile'],'_as_of':dt.datetime.now(dt.timezone.utc).isoformat()})
    bundle=checked('build_evidence_bundle',{'_tenant_id':tenant,'_run_id':run['run_id']})
    command('observe',{'bundle_id':bundle['bundle_id']},'operator')
   if 'decide' not in heads:command('decide',{'close_requested':True,'criteria_met':True,'material_contradiction':False,'reason':'[SINTÉTICO] Prova histórica não demonstra recuperação','reference':'urn:load:decision'})
   assert get('cw_operational_cases?id=eq.'+case)[0]['state']=='remain_open'
  company['case']=case
 with concurrent.futures.ThreadPoolExecutor(5) as pool:list(pool.map(cycles,companies[:10]))
 state_path.write_text(json.dumps(state));before=fingerprint()
 # Preparation is bounded; actual scheduler role claims and existing projection only.
 for c in companies[:10]:
  for _ in range(3):checked('prepare_scheduled_reviews',{'_tenant_id':c['tenant'],'_operation_id':newid()})
  checked('prepare_operational_notifications',{'_tenant_id':c['tenant']})
 assert fingerprint()==before
 calls={
  'onboarding':('operational_onboarding',{'_tenant_id':t}),
  'core_first_page':('core_followup_queue',{'_tenant_id':t}),
  'reviews_first_page':('scheduled_reviews',{'_tenant_id':t}),
  'private_inbox':('notification_inbox',{'_tenant_id':t}),
  'my_work':('my_operational_work',{'_tenant_id':t}),
 }
 measurements={}
 report['postgres_stats_before']=json.loads(sql("SELECT to_jsonb(x) FROM (SELECT numbackends,xact_commit,xact_rollback,blks_read,blks_hit,temp_files,temp_bytes,deadlocks FROM pg_stat_database WHERE datname='cw_e2e')x"))
 for label,(name,args) in calls.items():
  elapsed=[]
  for _ in range(5):
   started=time.monotonic();r=checked(name,args,'operator' if label in ('private_inbox','my_work') else 'admin');elapsed.append((time.monotonic()-started)*1000)
  measurements[label]={'n':len(elapsed),'median_ms':round(statistics.median(elapsed),3),'max_ms':round(max(elapsed),3)}
 report['queries']=measurements;save()
 # Exhaust actual keyset pages in the busiest tenant, not only a first-page smoke test.
 cursor='';seen=set();pages=0;started=time.monotonic()
 while True:
  r=checked('core_followup_queue',{'_tenant_id':t,'_after':cursor,'_limit':25})
  for item in r['items']:assert item['entry_key'] not in seen;seen.add(item['entry_key'])
  pages+=1
  if not r['has_more']:break
  cursor=r['next_cursor'];assert pages<50
 assert len(seen)==506,(len(seen),pages)  # 505 current assessments plus the case pinned to its historical opening evaluation.
 measurements['core_all_pages']={'pages':pages,'entries':len(seen),'elapsed_ms':round((time.monotonic()-started)*1000,3)}
 # Eight concurrent requests, three genuine role identities, independent company contexts.
 def one(n):
  role=['admin','operator','viewer'][n%3];company=companies[n%10];started=time.monotonic()
  result=checked('operational_onboarding',{'_tenant_id':company['tenant']},role);assert result['tenant_id']==company['tenant'] and result['role']==role
  return (time.monotonic()-started)*1000
 with concurrent.futures.ThreadPoolExecutor(8) as pool:latencies=list(pool.map(one,range(24)))
 measurements['concurrent_readers']={'requests':24,'concurrency':8,'authenticated_identities':3,'median_ms':round(statistics.median(latencies),3),'max_ms':round(max(latencies),3)}
 assert rpc('operational_onboarding',{'_tenant_id':companies[11]['tenant']},'viewer')[0]==403
 assert fingerprint()==before
 report['postgres_resources_snapshot']=json.loads(subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}',os.environ.get('PG_CONTAINER','cw-mvp-db')],text=True))
 report['postgres_stats_after']=json.loads(sql("SELECT to_jsonb(x) FROM (SELECT numbackends,xact_commit,xact_rollback,blks_read,blks_hit,temp_files,temp_bytes,deadlocks FROM pg_stat_database WHERE datname='cw_e2e')x"))
 report.update({'queries':measurements,'cases':10,'cycles':20,'resources_after':hardware()});save();print('PASS scale: 100 companies / 1,000 clients / 100,000 C01 observations; 10 cases / 20 cycles; keyset pagination, RLS and 8 concurrent readers. '+str(measurements),flush=True)
