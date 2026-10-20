"""Disposable real GoTrue/PostgREST onboarding. Never connects to hosted services."""
from pathlib import Path
exec(Path('e2e/operational-cycles.py').read_text().split('# Previous SQL/security suites')[0])
def ok(name,args,role='admin'):
 s,r=rpc(name,args,role);assert s in (200,204),(name,s,r);return r
# A genuinely new account, without memberships, for the independent browser journey.
password='Synthetic-'+newid()+'!9a';email='onboarding-'+newid()+'@example.invalid'
s,u=rest('/auth/v1/signup',{'email':email,'password':password},None);assert s==200 and u['user']['email_confirmed_at']
Path('e2e/private/onboarding-user.json').write_text(json.dumps({'email':email,'password':password,'id':u['user']['id']}))
# Separate HTTP scenario: real roles and an explicitly documented synthetic company.
t=ok('create_tenant',{'_name':'[SINTÉTICO] Novo onboarding HTTP','_subject_unit_type':'organization'})
for role in ['operator','viewer']:ok('add_tenant_member',{'_tenant_id':t,'_user_id':users[role]['id'],'_role':role})
def setup(role='admin',**kw):return ok('operational_onboarding',{'_tenant_id':t,**kw},role)
def axis(key):return next(i for i in setup(_subject_id=subject)['indicators'] if i['indicator_key']==key)
def fingerprint():return sql("SELECT md5(jsonb_build_array((SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_operational_cases x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM cw_operational_events x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM audit_log x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM c04_evaluations x),(SELECT jsonb_agg(to_jsonb(x) ORDER BY id) FROM observations x))::text)")
r=setup();assert r['approved_profile'] is None and r['subject'] is None and not r['indicators']
profile=ok('create_value_profile_draft',{'_tenant_id':t,'_promise':'[SINTÉTICO] Documentar redução de tempo'})
assert setup()['draft_profile']['issues']
assert rpc('approve_value_profile',{'_profile_id':profile})[0]==400
# Copy an already tested indicator contract, not any user/observation or profile approval.
template=get('profile_indicators?tenant_id=eq.'+atlas['tenant']+'&profile_id=eq.'+atlas['profile']+'&key=eq.cycle_minutes')[0]
for key in ['cycle_minutes','independent_minutes']:
 row={k:v for k,v in template.items() if k not in ['id','tenant_id','profile_id','created_at','updated_at']};row.update(tenant_id=t,profile_id=profile,key=key)
 assert rest('/rest/v1/profile_indicators',row)[0]==201
assert setup()['draft_profile']['issues']==[]
for role in ['operator','viewer']:assert rpc('approve_value_profile',{'_profile_id':profile},role)[0]==403
ok('approve_value_profile',{'_profile_id':profile});assert setup()['approved_profile']['id']==profile
s,rows=rest('/rest/v1/subjects?select=id',{'tenant_id':t,'external_ref':'first','display_name':'[SINTÉTICO] Primeiro cliente'});assert s==201;subject=rows[0]['id']
assert all(not i['has_observations'] and i['configuration'] is None for i in setup()['indicators'])
def config(key,compatibility='compatible'):
 return ok('save_c04_configuration',{'_tenant_id':t,'_subject_id':subject,'_profile_id':profile,'_indicator_key':key,'_previous_id':None,'_operation_id':newid(),'_definition':{**atlas['definition'],'compatibility':compatibility}})
c1=config('cycle_minutes');c2=config('independent_minutes','contradiction')
assert axis('independent_minutes')['configuration']['compatibility']=='contradiction' and not axis('cycle_minutes')['profile_changed']
# A real empty analysis/evidence/evaluation reports insufficient data, without manufacturing observations.
run=ok('run_deterioration_analysis',{'_tenant_id':t,'_subject_id':subject,'_expected_profile_id':profile})
b=ok('build_evidence_bundle',{'_tenant_id':t,'_run_id':run['run_id']})
e=ok('evaluate_c04_configuration',{'_tenant_id':t,'_configuration_id':c1,'_bundle_id':b['bundle_id']})
assert axis('cycle_minutes')['evaluation']['evidence']=='insufficient'
assert rpc('run_deterioration_analysis',{'_tenant_id':t,'_subject_id':subject,'_expected_profile_id':profile},'viewer')[0]==403
# CSV contract: valid original C01 import, preserving API/CSV equivalence and idempotence.
source=atlas['customers'][0];rows=get('observations?tenant_id=eq.'+atlas['tenant']+'&subject_id=eq.'+source['subject_id']+'&indicator_key=eq.cycle_minutes')
values=[{'line':n+1,'subject_external_ref':'first','indicator_key':'cycle_minutes','value_numeric':row['value_numeric'],'observed_at':row['observed_at'],'unit':row['unit'],'idempotency_key':newid()} for n,row in enumerate(rows)]
start=min(row['observed_at'] for row in rows);end=(max(dt.datetime.fromisoformat(row['observed_at']) for row in rows)+dt.timedelta(days=1)).isoformat()
body={'_tenant_id':t,'_expected_profile_id':profile,'_source':'synthetic-atlas','_coverage_start':start,'_coverage_end':end,'_coverage_declared':True,'_file_name':'[SINTÉTICO] onboarding.csv','_rows':values}
r=ok('import_observations',body);assert r['status']=='completed' and r['inserted']==len(values)
r=ok('import_observations',body);assert r['duplicates']==len(values) and r['inserted']==0
assert axis('cycle_minutes')['new_observations'] and not axis('independent_minutes')['has_observations']
# Use the same explicitly documented historical analysis instant as the synthetic source fixture.
bundle=get('c03_bundles?id=eq.'+source['bundle_id'])[0];asof=get('c02_runs?id=eq.'+bundle['run_id'])[0]['as_of']
run=ok('run_deterioration_analysis',{'_tenant_id':t,'_subject_id':subject,'_expected_profile_id':profile,'_as_of':asof})
b=ok('build_evidence_bundle',{'_tenant_id':t,'_run_id':run['run_id']});e=ok('evaluate_c04_configuration',{'_tenant_id':t,'_configuration_id':c1,'_bundle_id':b['bundle_id']})
a=axis('cycle_minutes');assert a['evaluation']['evidence']=='sufficient' and a['evaluation']['configuration_state']=='compatible'
assert axis('independent_minutes')['configuration']['compatibility']=='contradiction'
assert ok('evaluate_c04_configuration',{'_tenant_id':t,'_configuration_id':c1,'_bundle_id':b['bundle_id']})==e
assert get('cw_operational_cases?tenant_id=eq.'+t)==[]
# Read-only server projection, role/tenant/identity guards and pagination.
before=fingerprint()
for role in ['admin','operator','viewer']:
 r=setup(role);assert r['role']==role and r['subject']['id']==subject
 assert all(i['tenant_id']==t and i['subject_id']==subject for i in r['indicators'])
r=setup(_limit=1);assert r['has_more_indicators'];assert setup(_after_indicator=r['indicators'][0]['indicator_key'],_limit=1)['indicators'][0]['indicator_key']!=r['indicators'][0]['indicator_key']
assert fingerprint()==before,'Read projection mutated operational history'
for n in range(26):assert rest('/rest/v1/subjects',{'tenant_id':t,'external_ref':'page-'+str(n)})[0]==201
before=fingerprint()
r=setup(_limit=25);assert r['has_more_subjects'];nextpage=setup(_after_subject=r['subjects'][-1]['id'],_limit=25);assert nextpage['subjects'] and not set(i['id'] for i in nextpage['subjects'])&set(i['id'] for i in r['subjects'])
assert rpc('operational_onboarding',{'_tenant_id':t},'ownerB')[0]==403
assert rpc('operational_onboarding',{'_tenant_id':t},None)[0] in (401,403)
assert rpc('operational_onboarding',{'_tenant_id':t,'_subject_id':source['subject_id']})[0]==400
assert rpc('operational_onboarding',{'_tenant_id':t,'_limit':101})[0]==400
assert sql("SELECT prosecdef FROM pg_proc WHERE oid='public.operational_onboarding(uuid,uuid,uuid,text,integer)'::regprocedure")=='f'
assert fingerprint()==before,'Read projection mutated operational history'
print('PASS onboarding: real Auth/PostgREST, new tenant, draft issues and admin approval, absent/insufficient data, C01 replay, per-indicator contradiction, C02/C03/C04 sufficient evaluation, RLS/roles, bounded pagination and read-only preservation. Browser account has no memberships or synthetic business records yet.')
