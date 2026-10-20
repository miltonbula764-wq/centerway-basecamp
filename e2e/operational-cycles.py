"""Disposable PostgreSQL17 + real GoTrue/PostgREST; multiple cycles. No hosted connection."""
import concurrent.futures
import json
import os
import re
import time
import datetime as dt
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
    req=urllib.request.Request(cfg['url']+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers={'Prefer':'return=representation','Content-Type':'application/json','apikey':cfg['anon'],'Authorization':'Bearer '+(users[role]['token'] if role else cfg['anon'])})
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
f=atlas;t=f['tenant'];profile=f['profile'];template=f['customers'][0]
def ok(name,args,role='admin'):
    s,r=rpc(name,args,role);assert s==200,(name,s,r);return r
def get(path,role='admin'):
    s,r=rest('/rest/v1/'+path,None,role,'GET');assert s==200,(s,r);return r
# Previous SQL/security suites must also pass after 0021.
for suite, marker in [('permissions','CW_TEST_RESULTS'),('ingestion','CW_INGEST_RESULTS'),('c02','CW_C02_RESULTS'),('c03','CW_C03_RESULTS')]:
    r=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-f','supabase/tests/'+suite+'_test.sql'],env=env,text=True,capture_output=True)
    output=r.stdout+r.stderr
    Path('e2e/logs/cycles-regression-'+suite+'.log').write_text(output)
    assert r.returncode==3 and re.search(marker+r' pass=\d+ fail=0(?: |$)',output) and not re.search(r'not_run=[1-9]',output),suite+' regression failed (see log)'
    print(re.search(marker+r' pass=\d+ fail=0(?: not_run=0)?',output).group(0))
# Dedicated synthetic subject, preserving all existing journey/browser fixtures.
ref='cycles-'+newid();s,subjects=rest('/rest/v1/subjects?select=id',{'tenant_id':t,'external_ref':ref,'display_name':'[SINTÉTICO] Continuidade por ciclos'});assert s==201;subject=subjects[0]['id']
rows=get('observations?select=indicator_key,observed_at,value_numeric,value_text,unit,source&tenant_id=eq.'+t+'&subject_id=eq.'+template['subject_id'])
assert {r['source'] for r in rows}=={'synthetic-atlas'}
values=[{**{k:v for k,v in row.items() if k!='source' and v is not None},'subject_external_ref':ref,'line':i+1,'idempotency_key':newid()} for i,row in enumerate(rows)]
start=(min(dt.datetime.fromisoformat(r['observed_at']) for r in rows)-dt.timedelta(days=1)).isoformat();end=(max(dt.datetime.fromisoformat(r['observed_at']) for r in rows)+dt.timedelta(days=1)).isoformat()
result=ok('import_observations',{'_tenant_id':t,'_expected_profile_id':profile,'_source':'synthetic-atlas','_coverage_start':start,'_coverage_end':end,'_coverage_declared':True,'_file_name':'synthetic-cycles.csv','_rows':values});assert result['status']=='completed'
def clone_bundle(original):
    b=get('c03_bundles?select=run_id&tenant_id=eq.'+t+'&id=eq.'+original)[0]
    run=get('c02_runs?select=as_of&tenant_id=eq.'+t+'&id=eq.'+b['run_id'])[0]
    r=ok('run_deterioration_analysis',{'_tenant_id':t,'_subject_id':subject,'_expected_profile_id':profile,'_as_of':run['as_of']})
    return ok('build_evidence_bundle',{'_tenant_id':t,'_run_id':r['run_id']})['bundle_id']
before_bundle=clone_bundle(template['bundle_id']);after_bundle=clone_bundle(template['after_bundle_id'])
configuration=ok('save_c04_configuration',{'_tenant_id':t,'_subject_id':subject,'_profile_id':profile,'_indicator_key':'cycle_minutes','_previous_id':None,'_operation_id':newid(),'_definition':f['definition']})
evaluation=ok('evaluate_c04_configuration',{'_tenant_id':t,'_configuration_id':configuration,'_bundle_id':before_bundle})
opening={'eligible':True,'configuration_pinned':True,'eligibility_reason':'[SINTÉTICO] Revisão humana individual','eligibility_ref':'urn:cycles:opening','opening_criteria':'[SINTÉTICO] Lacuna documentada','closure_criteria':'[SINTÉTICO] Objetivo histórico, prova pós-execução e revisão humana','closure_ref':'urn:cycles:closure'}
case=ok('open_operational_case',{'_tenant_id':t,'_evaluation_id':evaluation,'_operation_id':newid(),'_definition':opening})
identity=get('cw_operational_cases?tenant_id=eq.'+t+'&id=eq.'+case)[0]
proof=get('observations?select=id&tenant_id=eq.'+t+'&subject_id=eq.'+subject+'&indicator_key=eq.workflow_fact')[0]['id']
def current():return get('cw_operational_cases?tenant_id=eq.'+t+'&id=eq.'+case)[0]
def args(command,payload,version=None,operation=None):return {'_tenant_id':t,'_case_id':case,'_expected_version':current()['version'] if version is None else version,'_operation_id':operation or newid(),'_command':command,'_payload':payload}
def cmd(command,payload,role='admin'):
    a=args(command,payload);return ok('command_operational_case',a,role),a
def history(**kw):return ok('operational_cycle_history',{'_tenant_id':t,'_case_id':case,**kw})
plan={'action':'[SINTÉTICO] Pessoa ajusta configuração','rationale':'[SINTÉTICO] Facto revisto por pessoa','success_conditions':'Objetivo histórico demonstrado com medições posteriores','limitations':'Sem atribuição automática de causalidade','reversal':'Revisão humana antes da reversão','reference':'urn:cycles:plan','observation_seconds':1}
finding={'status':'confirmed','finding':'[SINTÉTICO] Impedimento confirmado por revisão humana','reference':'urn:cycles:investigation','observation_ids':[proof]}
continuation={'reason':'[SINTÉTICO] Decisão humana de continuar a investigação, sem prova de recuperação','reference':'urn:cycles:continuation'}
decision={'close_requested':True,'criteria_met':True,'material_contradiction':False,'reason':'[SINTÉTICO] Revisão dos critérios históricos','reference':'urn:cycles:decision'}
first=history()['current'];assert first['id']==case and first['number']==1
first_receipt=None;execution_ids=[];approval_ids=[]
for number in (1,2):
    h=history();assert h['current']['number']==number
    if number==2:
        # A new cycle has no inherited stage or capability, even if the old approval is still in time.
        assert set(h['heads'])=={'start_cycle'}
        for command,payload in [('plan',plan),('approve',{'valid_until':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),'reason':'x','reference':'urn:cycles:wrong'}),('record_execution',{'receipt':'x','reference':'urn:cycles:wrong'}),('observe',{'bundle_id':after_bundle}),('decide',decision)]:
            s,r=rpc('command_operational_case',args(command,payload));assert s==400 and r['code']=='22023',(command,s,r)
    cmd('investigate',finding,'operator');cmd('plan',plan,'operator')
    approval={'valid_until':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),'reason':'[SINTÉTICO] Nova autorização deste plano e ciclo','reference':'urn:cycles:approval'}
    assert rpc('command_operational_case',args('approve',approval),'operator')[0]==403
    if number==2:
        s,r=rpc('command_operational_case',args('approve',{**approval,'plan_event_id':history(_cycle_id=first['id'])['heads']['plan']['id']}));assert s==400
    approval_id,_=cmd('approve',approval);approval_ids.append(approval_id)
    receipt,a=cmd('record_execution',{'receipt':'[SINTÉTICO] Pessoa regista execução; não comprova valor','reference':'urn:cycles:receipt'},'operator');execution_ids.append(receipt)
    if first_receipt is None:first_receipt=(receipt,a)
    execution=history()['heads']['record_execution'];assert execution['details']['cycle_id']==h['current']['id'] and execution['details']['approval_event_id']==approval_id
    s,r=rpc('command_operational_case',args('observe',{'bundle_id':after_bundle}),'operator');assert s==400 and r['message']=='observation_window_not_elapsed'
    # The same cycle cannot execute a second time.
    assert rpc('command_operational_case',args('record_execution',{'receipt':'x','reference':'urn:cycles:duplicate'}),'operator')[0]==400
    time.sleep(1.1)  # Real, explicitly configured one-second test window; no clock alteration.
    cmd('observe',{'bundle_id':after_bundle},'operator')
    comparison=history()['heads']['observe'];assert comparison['details']['sufficient'] is False and comparison['details']['result']=='inconclusive'
    assert comparison['details']['executed_at']==execution['details']['executed_at'] and comparison['details']['wait_until']==execution['details']['wait_until']
    cmd('decide',decision);assert current()['state']=='remain_open'
    if number==1:
        historical_rows=get('cw_operational_events?tenant_id=eq.'+t+'&case_id=eq.'+case+'&order=sequence')
        for role in ['operator','viewer','ownerB',None]:assert rpc('command_operational_case',args('start_cycle',continuation),role)[0] in (401,403)
        assert rpc('command_operational_case',args('start_cycle',{'reason':'','reference':'bad'}))[0]==400
        a=args('start_cycle',continuation)
        with concurrent.futures.ThreadPoolExecutor(4) as pool:out=list(pool.map(lambda _:rpc('command_operational_case',a),range(4)))
        assert all(s==200 and r==out[0][1] for s,r in out),out
        assert current()['state']=='investigation'
        assert len(get('cw_operational_cycles?tenant_id=eq.'+t+'&case_id=eq.'+case))==2
        s,r=rpc('command_operational_case',args('start_cycle',continuation));assert s==400 and r['message']=='remain_open_required'
        q=ok('core_followup_queue',{'_tenant_id':t,'_client':ref})['items'];q=next(q for q in q if q['case_id']==case)
        assert q['next_action']=='investigate' and q['review_at'] is None and q['basis']['cycle_number']==2 and not q['basis']['authorization_valid']
        ok('prepare_scheduled_reviews',{'_tenant_id':t,'_operation_id':newid()});ok('prepare_scheduled_reviews',{'_tenant_id':t,'_operation_id':newid()});ok('prepare_scheduled_reviews',{'_tenant_id':t,'_operation_id':newid()})
        monitor=ok('scheduled_reviews',{'_tenant_id':t,'_limit':100})['items'];mon=next(x for x in monitor if x['source'].get('case_id')==case)
        assert mon['source']['basis']['cycle_number']==2 and mon['facts']['review_at'] is None
assert len(set(execution_ids))==2 and len(set(approval_ids))==2
# Distinct competing operations: one new cycle, the stale version cannot advance it twice.
version=current()['version'];calls=[args('start_cycle',continuation,version=version) for _ in range(2)]
with concurrent.futures.ThreadPoolExecutor(2) as pool:out=list(pool.map(lambda a:rpc('command_operational_case',a),calls))
assert sorted(s for s,r in out)==[200,409],out
assert history()['current']['number']==3
state=current();assert ok('command_operational_case',first_receipt[1],'operator')==first_receipt[0];assert current()==state
changed={**first_receipt[1],'_payload':{'receipt':'different','reference':'urn:cycles:receipt'}};assert rpc('command_operational_case',changed,'operator')[0]==400
# Previous cycles and original case identity survive unchanged.
assert get('cw_operational_events?tenant_id=eq.'+t+'&case_id=eq.'+case+'&sequence=lte.'+str(historical_rows[-1]['sequence'])+'&order=sequence')==historical_rows
assert {k:v for k,v in state.items() if k not in ('state','version')}=={k:v for k,v in identity.items() if k not in ('state','version')}
assert history(_cycle_id=first['id'])['heads']['record_execution']['id']==first_receipt[0]
assert history(_cycle_id=first['id'])['heads']['decide']['to_state']=='remain_open'
h=history(_limit=2);assert h['has_more_cycles'] and len(h['cycles'])==2;assert history(_before_cycle=h['cycles'][-1]['number'],_limit=2)['cycles'][0]['number']==1
seen=[];after=-1
while True:
    p=history(_cycle_id=first['id'],_after_event=after,_limit=2);seen+=p['events']
    if not p['has_more_events']:break
    after=p['events'][-1]['sequence']
assert seen==historical_rows
# RLS/auth and read-only history; guessing a foreign cycle never selects it.
assert rpc('operational_cycle_history',{'_tenant_id':t,'_case_id':case},'ownerB')[0]==403
foreign=get('cw_operational_cycles?tenant_id=eq.'+t+'&case_id=neq.'+case+'&limit=1')[0]['id']
assert rpc('operational_cycle_history',{'_tenant_id':t,'_case_id':case,'_cycle_id':foreign})[0]==400
for role in ['admin','operator','viewer']:
    assert rpc('operational_cycle_history',{'_tenant_id':t,'_case_id':case},role)[0]==200
    assert rest('/rest/v1/cw_operational_cycles',{},role)[0]==403
assert get('cw_operational_cycles?tenant_id=eq.'+t,'ownerB')==[]
rows_before=sql('SELECT md5(jsonb_agg(to_jsonb(x) ORDER BY sequence)::text) FROM cw_operational_events x WHERE case_id='+lit(case))
for _ in range(3):history()
assert rows_before==sql('SELECT md5(jsonb_agg(to_jsonb(x) ORDER BY sequence)::text) FROM cw_operational_events x WHERE case_id='+lit(case))
sql("BEGIN; DO $$ BEGIN BEGIN UPDATE public.cw_operational_cycles SET reason=reason; RAISE EXCEPTION 'cycles mutable'; EXCEPTION WHEN SQLSTATE '42501' THEN NULL; END; END $$; ROLLBACK;")
Path('e2e/cycle-fixtures.json').write_text(json.dumps({'tenant':t,'subject':subject,'case':case,'configuration':configuration,'evaluation':evaluation,'proof':proof,'after_bundle':after_bundle,'first_cycle':first['id']}))
print('PASS cycles: real GoTrue/PostgREST, two complete prospective cycles and human start of third; independent authorization/execution/window, historical evidence inconclusive, unchanged original identity/history, version conflicts, concurrent replay/start, RLS/roles, paginated history, Central and scheduled monitoring current-cycle scope.')

# SQL role/claim probes below are distinct from the real HTTP authentication above; always rolled back.
sql("BEGIN; SELECT set_config('cw.cycle_fixture',"+lit(json.dumps({'tenant':t,'case':case,'subject':subject,'configuration':configuration,'actor':users['admin']['id'],'proof':proof,'after_bundle':after_bundle}))+",true);"+r'''
DO $probe$
DECLARE f jsonb:=current_setting('cw.cycle_fixture')::jsonb; c public.cw_operational_cases;cfg public.c04_configurations;new_config uuid;
BEGIN
 SELECT * INTO c FROM public.cw_operational_cases WHERE id=(f->>'case')::uuid;
 SELECT * INTO cfg FROM public.c04_configurations WHERE id=c.configuration_id;
 -- Fixture is in investigation. No second active cycle can be created, even with a current version.
 PERFORM set_config('request.jwt.claims',jsonb_build_object('role','authenticated','sub',f->>'actor')::text,true);
 SET LOCAL ROLE authenticated;
 BEGIN PERFORM public.command_operational_case(c.tenant_id,c.id,c.version,gen_random_uuid(),'start_cycle','{"reason":"[SYNTHETIC] denied overlap","reference":"urn:cycles:overlap"}'); RAISE EXCEPTION 'active cycle overlapped'; EXCEPTION WHEN SQLSTATE '22023' THEN NULL; END;
 RESET ROLE;
 -- Complete a third cycle inside this rolled-back transaction, then test a revised contract.
 CREATE FUNCTION pg_temp.cycle_probe_cmd(_case uuid,_command text,_payload jsonb) RETURNS void LANGUAGE plpgsql AS $fn$
 DECLARE c public.cw_operational_cases; BEGIN
  SELECT * INTO c FROM public.cw_operational_cases WHERE id=_case;
  PERFORM public.command_operational_case(c.tenant_id,c.id,c.version,gen_random_uuid(),_command,_payload);
 END $fn$;
 SET LOCAL ROLE authenticated;
 PERFORM pg_temp.cycle_probe_cmd(c.id,'investigate',jsonb_build_object('status','confirmed','finding','[SYNTHETIC] third cycle probe','reference','urn:cycles:probe','observation_ids',jsonb_build_array(f->>'proof')));
 PERFORM pg_temp.cycle_probe_cmd(c.id,'plan','{"action":"[SYNTHETIC] human change","rationale":"probe","success_conditions":"historical goal","limitations":"no causality","reversal":"human review","reference":"urn:cycles:plan","observation_seconds":1}');
 PERFORM pg_temp.cycle_probe_cmd(c.id,'approve',jsonb_build_object('valid_until',clock_timestamp()+interval '1 hour','reason','[SYNTHETIC] new approval','reference','urn:cycles:approval'));
 PERFORM pg_temp.cycle_probe_cmd(c.id,'record_execution','{"receipt":"[SYNTHETIC] human receipt","reference":"urn:cycles:receipt"}');
 PERFORM pg_sleep(1.1);
 PERFORM pg_temp.cycle_probe_cmd(c.id,'observe',jsonb_build_object('bundle_id',f->>'after_bundle'));
 PERFORM pg_temp.cycle_probe_cmd(c.id,'decide','{"close_requested":true,"criteria_met":true,"material_contradiction":false,"reason":"[SYNTHETIC] historical proof insufficient","reference":"urn:cycles:decision"}');
 RESET ROLE;
 SELECT * INTO c FROM public.cw_operational_cases WHERE id=c.id;
 IF c.state<>'remain_open' THEN RAISE EXCEPTION 'insufficient third cycle closed'; END IF;
 -- A newer C04 configuration cannot silently replace the case's pinned goal.
 SET LOCAL ROLE authenticated;
 new_config:=public.save_c04_configuration(c.tenant_id,c.subject_id,cfg.profile_id,cfg.indicator_key,cfg.id,gen_random_uuid(),cfg.definition||'{"customer_goal":"[SYNTHETIC] revised goal"}');
 RESET ROLE;
 SET LOCAL ROLE authenticated;
 BEGIN
  PERFORM public.command_operational_case(c.tenant_id,c.id,c.version,gen_random_uuid(),'start_cycle','{"reason":"[SYNTHETIC] revised contract blocked","reference":"urn:cycles:revision"}');
  RAISE EXCEPTION 'revised contract accepted';
 EXCEPTION WHEN SQLSTATE '22023' THEN
  IF SQLERRM<>'configuration_revision_requires_review' THEN RAISE; END IF;
 END;
 RESET ROLE;
 IF (SELECT configuration_id FROM public.cw_operational_cases WHERE id=c.id)<>cfg.id THEN RAISE EXCEPTION 'pinned identity changed'; END IF;
END $probe$;
ROLLBACK;
''')

sql("BEGIN; SELECT set_config('cw.cycle_history_fixture',"+lit(json.dumps(f))+",true);"+Path('e2e/cycles-history-review.sql').read_text()+"\nROLLBACK;")
print('PASS second-cycle closure: explicitly synthetic retrospective fixture, real SQL roles/claims for C09-C10, sufficient evidence required and reopening denied; all writes rolled back.')
