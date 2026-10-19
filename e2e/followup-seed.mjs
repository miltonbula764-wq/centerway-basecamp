// Synthetic real-auth fixtures for queue scale and independent indicator states; no historical fabrication.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
const cfg=JSON.parse(fs.readFileSync('e2e/private/public.json'));
assert.equal(cfg.url,'http://127.0.0.1:54321');
const users=JSON.parse(fs.readFileSync('e2e/private/mvp-users.json'));
async function request(path,token,body,method='POST'){
 const r=await fetch(cfg.url+path,{method,headers:{apikey:cfg.anon,Authorization:`Bearer ${token||cfg.anon}`,'Content-Type':'application/json',Prefer:'return=representation'},...(body===undefined?{}:{body:JSON.stringify(body)})});
 const text=await r.text();assert.ok(r.ok,`${path}: ${r.status} ${text}`);return text?JSON.parse(text):null;
}
const rpc=(token,name,body)=>request('/rest/v1/rpc/'+name,token,body);
const token=(await request('/auth/v1/token?grant_type=password',null,{email:users.admin.email,password:users.admin.password})).access_token;
const tenant=await rpc(token,'create_tenant',{_name:'[SINTÉTICO] Central SaaS',_subject_unit_type:'organization'});
for(const role of ['operator','viewer']) await rpc(token,'add_tenant_member',{_tenant_id:tenant,_user_id:users[role].id,_role:role});
const profile=await rpc(token,'create_value_profile_draft',{_tenant_id:tenant,_promise:'[SINTÉTICO] Três indicadores independentes documentados',_expected_outcome:'Avaliação individual sem score global'});
const atlas=JSON.parse(fs.readFileSync('e2e/operational-fixtures.json'));
const [template]=await request(`/rest/v1/profile_indicators?tenant_id=eq.${atlas.tenant}&profile_id=eq.${atlas.profile}&key=eq.cycle_minutes`,token,undefined,'GET');
const {id,created_at,updated_at,...indicator}=template;
const keys=['contradiction_minutes','independent_minutes','partial_minutes'];
for(const key of keys) await request('/rest/v1/profile_indicators',token,{...indicator,tenant_id:tenant,profile_id:profile,key,name:'[SINTÉTICO] '+key});
await rpc(token,'approve_value_profile',{_profile_id:profile});
const subjects=await request('/rest/v1/subjects?select=id,external_ref,display_name',token,Array.from({length:102},(_,i)=>({tenant_id:tenant,external_ref:`queue-${String(i).padStart(3,'0')}`,display_name:`[SINTÉTICO] Cliente ${String(i).padStart(3,'0')}`})));
const customer=subjects.find(s=>s.external_ref==='queue-000');
const midnight=new Date();midnight.setUTCHours(0,0,0,0);const date=d=>new Date(+midnight+d*86400000).toISOString();
const rows=keys.flatMap((key,index)=>[-28,-27,-26].map((day,i)=>({line:index*3+i+1,subject_external_ref:customer.external_ref,indicator_key:key,value_numeric:'90',unit:'min',observed_at:date(day),idempotency_key:randomUUID()})));
const imported=await rpc(token,'import_observations',{_tenant_id:tenant,_expected_profile_id:profile,_source:'synthetic-atlas',_coverage_start:date(-40),_coverage_end:date(0),_coverage_declared:true,_file_name:'synthetic-queue.csv',_rows:rows});assert.equal(imported.status,'completed');
const run=await rpc(token,'run_deterioration_analysis',{_tenant_id:tenant,_subject_id:customer.id,_expected_profile_id:profile,_as_of:date(-25)});
const bundle=await rpc(token,'build_evidence_bundle',{_tenant_id:tenant,_run_id:run.run_id});assert.equal(bundle.status,'built');
const evaluations={};
for(const key of keys){
 const def={...atlas.definition,...(key.startsWith('contradiction')?{compatibility:'contradiction',compatibility_ref:'urn:queue:documented:contradiction'}:key.startsWith('partial')?{customer_ref:null}:{})};
 const configuration=await rpc(token,'save_c04_configuration',{_tenant_id:tenant,_subject_id:customer.id,_profile_id:profile,_indicator_key:key,_previous_id:null,_operation_id:randomUUID(),_definition:def});
 evaluations[key]=await rpc(token,'evaluate_c04_configuration',{_tenant_id:tenant,_configuration_id:configuration,_bundle_id:bundle.bundle_id});
}
const operatorToken=(await request('/auth/v1/token?grant_type=password',null,{email:users.operator.email,password:users.operator.password})).access_token;
const foreignTenant=await rpc(operatorToken,'create_tenant',{_name:'[SINTÉTICO] Restrita ao operador','_subject_unit_type':'organization'});
fs.writeFileSync('e2e/followup-fixtures.json',JSON.stringify({tenant,profile,customer,subjects,evaluations,foreignTenant,actor:users.admin.id,operator:users.operator.id,viewer:users.viewer.id},null,2));
console.log('Follow-up fixtures persisted through real authentication: 102 clients, three independent indicators, contradiction, sufficient and insufficient C04.');
