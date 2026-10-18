// Synthetic non-FlowReports SaaS. All profile, C01-C04 data use real authenticated REST/RPCs.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
const config=JSON.parse(fs.readFileSync('e2e/private/public.json'));
assert.equal(config.url,'http://127.0.0.1:54321');
const credentials=JSON.parse(fs.readFileSync('e2e/private/mvp-users.json'));
async function request(path, token, body, method='POST') {
 const r=await fetch(config.url+path,{method,headers:{apikey:config.anon,Authorization:`Bearer ${token||config.anon}`,'Content-Type':'application/json',Prefer:'return=representation'},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const text=await r.text(); if(!r.ok) throw Error(`${method} ${path}: ${r.status} ${text}`); return text?JSON.parse(text):null;
}
const rpc=(token,name,body)=>request('/rest/v1/rpc/'+name,token,body);
const users={};
for(const role of ['admin','operator','viewer']) {
 const u=credentials[role];const s=await request('/auth/v1/token?grant_type=password',null,{email:u.email,password:u.password});users[role]={id:s.user.id,token:s.access_token};
}
const token=users.admin.token;
const tenant=await rpc(token,'create_tenant',{_name:'Atlas SaaS · SINTÉTICO operacional',_subject_unit_type:'organization'});
for(const role of ['operator','viewer']) await rpc(token,'add_tenant_member',{_tenant_id:tenant,_user_id:users[role].id,_role:role});
const profile=await rpc(token,'create_value_profile_draft',{_tenant_id:tenant,_promise:'[SINTÉTICO] Processamento documentado no plano Atlas.',_expected_outcome:'Metas individuais por cliente, sem promessa global inferida.'});
await request('/rest/v1/profile_indicators',token,{tenant_id:tenant,profile_id:profile,key:'cycle_minutes',name:'Duração do ciclo',classification:'outcome',value_type:'numeric',unit:'min',direction:'lower_is_better',baseline_method:'fixed_value',baseline_value:100,baseline_min_period_days:1,observation_window_days:1,comparison_window_days:1,min_coverage_pct:100,min_denominator:1,target_value:60,deterioration_kind:'absolute',deterioration_operator:'gt',deterioration_value:150,deterioration_consecutive_windows:2,recovery_kind:'absolute',recovery_operator:'lte',recovery_value:60,recovery_consecutive_windows:2,aggregation:'mean',expected_cadence_days:1,denominator_mode:'observation_count'});
await request('/rest/v1/profile_indicators',token,{tenant_id:tenant,profile_id:profile,key:'workflow_fact',name:'Condição documentada',classification:'context',value_type:'text',unit:'estado',direction:'higher_is_better'});
await rpc(token,'approve_value_profile',{_profile_id:profile});
const midnight=new Date();midnight.setUTCHours(0,0,0,0);
const date=days=>new Date(+midnight+days*86400000).toISOString();
const definition={promise:'[SINTÉTICO] Processamento documentado',promise_ref:'urn:atlas:promise:1',plan_capability:'[SINTÉTICO] Inclui processo manual de configuração',plan_ref:'urn:atlas:plan:1',customer_goal:'[SINTÉTICO] Ciclo até 60 minutos',customer_ref:'urn:atlas:customer:1',compatibility:'compatible',compatibility_ref:'urn:atlas:review:1',unit:'min',source:'synthetic-atlas',aggregation:'mean',comparator:'lte',target:60,deadline:date(-30),observation_start:date(-40),window_count:2};
const customers=[];
for(const stage of ['prospective','historical_resolved','historical_unmet']) {
 const [s]=await request('/rest/v1/subjects?select=id',token,{tenant_id:tenant,external_ref:'atlas-'+stage,display_name:'[SINTÉTICO] Atlas · '+stage});
 const values=stage==='historical_unmet'?[100,95,90,90,85,80]:[100,95,90,75,50,45];
 const rows=[-28,-27,-26,-4,-3,-2].map((day,i)=>({line:i+1,subject_external_ref:'atlas-'+stage,indicator_key:'cycle_minutes',value_numeric:String(values[i]),unit:'min',observed_at:date(day),idempotency_key:randomUUID()}));
 rows.push({line:7,subject_external_ref:'atlas-'+stage,indicator_key:'workflow_fact',value_text:'documented-blocker',unit:'estado',observed_at:date(-26),idempotency_key:randomUUID()});
 const imported=await rpc(token,'import_observations',{_tenant_id:tenant,_expected_profile_id:profile,_source:'synthetic-atlas',_coverage_start:date(-40),_coverage_end:date(0),_coverage_declared:true,_file_name:'synthetic-atlas.csv',_rows:rows});assert.equal(imported.status,'completed');
 const initial=await rpc(token,'run_deterioration_analysis',{_tenant_id:tenant,_subject_id:s.id,_expected_profile_id:profile,_as_of:date(-25)});
 const [signal]=await request(`/rest/v1/c02_results?select=status&run_id=eq.${initial.run_id}&indicator_key=eq.cycle_minutes`,token,undefined,'GET');assert.equal(signal.status,'no_deterioration','Case entry must not require a deterioration candidate');
 const b=await rpc(token,'build_evidence_bundle',{_tenant_id:tenant,_run_id:initial.run_id});assert.equal(b.status,'built');
 const after=await rpc(token,'run_deterioration_analysis',{_tenant_id:tenant,_subject_id:s.id,_expected_profile_id:profile,_as_of:date(-1)});
 const ab=await rpc(token,'build_evidence_bundle',{_tenant_id:tenant,_run_id:after.run_id});assert.equal(ab.status,'built');
 const configuration=await rpc(token,'save_c04_configuration',{_tenant_id:tenant,_subject_id:s.id,_profile_id:profile,_indicator_key:'cycle_minutes',_previous_id:null,_operation_id:randomUUID(),_definition:definition});
 const evaluation=await rpc(token,'evaluate_c04_configuration',{_tenant_id:tenant,_configuration_id:configuration,_bundle_id:b.bundle_id});
 const [a]=await request(`/rest/v1/c04_evaluations?select=result,evidence,configuration_state&id=eq.${evaluation}`,token,undefined,'GET');assert.equal(a.result,'not_achieved');assert.equal(a.evidence,'sufficient');
 const [proof]=await request(`/rest/v1/observations?select=id&subject_id=eq.${s.id}&indicator_key=eq.workflow_fact`,token,undefined,'GET');
 customers.push({stage,subject_id:s.id,configuration_id:configuration,evaluation_id:evaluation,bundle_id:b.bundle_id,after_bundle_id:ab.bundle_id,proof_id:proof.id});
}
// A persisted inconclusive entry must remain visible and never silently open a case.
const partial={...definition,customer_ref:null};const s=customers[2];
const incomplete=await rpc(token,'save_c04_configuration',{_tenant_id:tenant,_subject_id:s.subject_id,_profile_id:profile,_indicator_key:'cycle_minutes',_previous_id:s.configuration_id,_operation_id:randomUUID(),_definition:partial});
const incompleteEvaluation=await rpc(token,'evaluate_c04_configuration',{_tenant_id:tenant,_configuration_id:incomplete,_bundle_id:s.bundle_id});
// Restore documentation in a new version; history is retained.
const restored=await rpc(token,'save_c04_configuration',{_tenant_id:tenant,_subject_id:s.subject_id,_profile_id:profile,_indicator_key:'cycle_minutes',_previous_id:incomplete,_operation_id:randomUUID(),_definition:definition});
s.configuration_id=restored;s.evaluation_id=await rpc(token,'evaluate_c04_configuration',{_tenant_id:tenant,_configuration_id:restored,_bundle_id:s.bundle_id});
fs.writeFileSync('e2e/operational-fixtures.json',JSON.stringify({tenant,profile,actor:users.admin.id,operator:users.operator.id,viewer:users.viewer.id,definition,customers,incompleteEvaluation,executed_at:date(-10)},null,2));
console.log('Non-FlowReports C01-C04 operational inputs persisted under real Auth. C02 no_deterioration verified; partial entry retained.');
