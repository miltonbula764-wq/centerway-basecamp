// Disposable backend only. Real Auth/REST for C01-C06; retrospective C07/C08 fixtures are separate.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
const config = JSON.parse(fs.readFileSync('e2e/private/public.json','utf8'));
assert.equal(config.url,'http://127.0.0.1:54321');
const password=randomBytes(24).toString('base64url')+'-Aa1!';
async function request(path, token, body, method='POST') {
  const r=await fetch(config.url+path,{method,headers:{apikey:config.anon,Authorization:`Bearer ${token||config.anon}`,'Content-Type':'application/json',Prefer:'return=representation'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const text=await r.text(); if(!r.ok) throw Error(`${method} ${path}: ${r.status} ${text}`); return text?JSON.parse(text):null;
}
const rpc=(token,name,body)=>request('/rest/v1/rpc/'+name,token,body);
const users={};
for(const role of ['admin','operator','viewer']) {
  const email=`mvp-${role}@example.invalid`;
  await request('/auth/v1/signup',null,{email,password});
  const session=await request('/auth/v1/token?grant_type=password',null,{email,password});
  assert.ok(session.access_token); users[role]={email,password,id:session.user.id,token:session.access_token};
}
const token=users.admin.token;
const tenant=await rpc(token,'create_tenant',{_name:'FlowReports · MVP SINTÉTICO',_subject_unit_type:'organization'});
for(const role of ['operator','viewer']) await rpc(token,'add_tenant_member',{_tenant_id:tenant,_user_id:users[role].id,_role:role});
const profile=await rpc(token,'create_value_profile_draft',{_tenant_id:tenant,_promise:'[SINTÉTICO] Automatização de relatórios com integração ativa.',_expected_outcome:'Objetivo individual confirmado: reduzir de 10 para 4 h/semana.'});
await request('/rest/v1/profile_indicators',token,{tenant_id:tenant,profile_id:profile,key:'report_hours',name:'Horas semanais de relatórios',classification:'outcome',value_type:'numeric',unit:'h/semana',direction:'lower_is_better',baseline_method:'fixed_value',baseline_value:10,baseline_min_period_days:7,observation_window_days:7,comparison_window_days:7,min_coverage_pct:100,min_denominator:1,target_value:4,deterioration_kind:'absolute',deterioration_operator:'gt',deterioration_value:6,deterioration_consecutive_windows:2,recovery_kind:'absolute',recovery_operator:'lte',recovery_value:4,recovery_consecutive_windows:2,aggregation:'mean',expected_cadence_days:7,denominator_mode:'observation_count'});
await request('/rest/v1/profile_indicators',token,{tenant_id:tenant,profile_id:profile,key:'integration_status',name:'Estado documentado da integração',classification:'context',value_type:'text',unit:'estado',direction:'higher_is_better'});
await rpc(token,'approve_value_profile',{_profile_id:profile});
const midnight=new Date();midnight.setUTCHours(0,0,0,0);
const date=days=>new Date(+midnight+days*86400000).toISOString();
const fixture={tenant,profile,actor:users.admin.id,executed_at:date(-34),cases:[]};
for(const [name,stage,post] of [
  ['Loja Aurora · investigar','investigation',4],['Loja Aurora · aprovar','approval',4],
  ['Loja Aurora · executar','execution',4],['Loja Aurora · em observação','waiting',4],
  ['Loja Aurora · resultado atingido','historical_resolved',4],['Loja Aurora · objetivo por atingir','historical_open',9],
]) {
  const external_ref='mvp-'+stage;
  const [subject]=await request('/rest/v1/subjects?select=id',token,{tenant_id:tenant,external_ref,display_name:name});
  let rows=[[-70,10],[-63,8],[-56,6],[-49,7],[-42,9],[-28,9],[-21,post],[-14,post]].map(([day,value],i)=>({line:i+1,subject_external_ref:external_ref,indicator_key:'report_hours',unit:'h/semana',value_numeric:String(value),observed_at:date(day),idempotency_key:external_ref+'-hours-'+i}));
  rows.push({line:9,subject_external_ref:external_ref,indicator_key:'integration_status',unit:'estado',value_text:'disabled',observed_at:date(-47),idempotency_key:external_ref+'-disabled'});
  if(stage.startsWith('historical')) rows.push({line:10,subject_external_ref:external_ref,indicator_key:'integration_status',unit:'estado',value_text:'enabled',observed_at:date(-30),idempotency_key:external_ref+'-enabled'});
  const imported=await rpc(token,'import_observations',{_tenant_id:tenant,_expected_profile_id:profile,_source:'synthetic-flowreports',_coverage_start:date(-80),_coverage_end:date(0),_coverage_declared:true,_file_name:'mvp-synthetic.csv',_rows:rows});
  assert.equal(imported.status,'completed',JSON.stringify(imported));
  const run=await rpc(token,'run_deterioration_analysis',{_tenant_id:tenant,_subject_id:subject.id,_expected_profile_id:profile,_as_of:date(-35)});
  const bundle=await rpc(token,'build_evidence_bundle',{_tenant_id:tenant,_run_id:run.run_id}); assert.equal(bundle.status,'built');
  const objective=await rpc(token,'create_demo_objective',{_tenant_id:tenant,_subject_id:subject.id,_profile_id:profile,_deadline:date(-36),_source:'synthetic-flowreports',_capacity_ref:'[SINTÉTICO] Plano diário v1',_commitment_ref:'[SINTÉTICO] Compromisso compatível v1',_customer_ref:'[SINTÉTICO] Aurora confirmou 10→4h em seis semanas'});
  const assessment=await rpc(token,'assess_demo_objective',{_tenant_id:tenant,_objective_id:objective,_bundle_id:bundle.bundle_id});
  const [a]=await request('/rest/v1/cw_assessments?id=eq.'+assessment,token,undefined,'GET'); assert.equal(a.result,'not_achieved');
  const proof=await request(`/rest/v1/observations?subject_id=eq.${subject.id}&value_text=eq.disabled&select=id`,token,undefined,'GET');
  let caseId=null,version=0;
  async function command(command,payload={}) { const e=await rpc(token,'command_demo_case',{_tenant_id:tenant,_case_id:caseId,_expected_version:version,_operation_id:crypto.randomUUID(),_command:command,_payload:payload}); version=e.sequence; return e; }
  if(!stage.startsWith('historical')) {
    caseId=await rpc(token,'open_demo_case',{_tenant_id:tenant,_assessment_id:assessment});
    if(stage!=='investigation') { await command('investigate',{observation_id:proof[0].id});await command('plan'); }
    if(['execution','waiting'].includes(stage)) await command('approve');
    if(stage==='waiting') await command('record_execution',{receipt:'[SINTÉTICO] Tarefa humana DEMO-001, registo sem conector externo.'});
  }
  let afterBundle=null;
  if(stage.startsWith('historical')) {
    const afterRun=await rpc(token,'run_deterioration_analysis',{_tenant_id:tenant,_subject_id:subject.id,_expected_profile_id:profile,_as_of:date(-7)});
    afterBundle=await rpc(token,'build_evidence_bundle',{_tenant_id:tenant,_run_id:afterRun.run_id}); assert.equal(afterBundle.status,'built');
  }
  fixture.cases.push({name,stage,subject_id:subject.id,assessment_id:assessment,objective_id:objective,bundle_id:bundle.bundle_id,proof_id:proof[0].id,case_id:caseId,after_bundle_id:afterBundle?.bundle_id});
}
fs.writeFileSync('e2e/private/mvp-users.json',JSON.stringify(Object.fromEntries(Object.entries(users).map(([r,u])=>[r,{email:u.email,password:u.password,id:u.id}]))),{mode:0o600});
fs.writeFileSync('e2e/mvp-fixtures.json',JSON.stringify(fixture,null,2));
console.log('MVP mounted with real Auth/RPCs for C01-C08 prospective paths. Historical outcome fixtures still require e2e/mvp-history.sql; these are explicitly retrospective, not an elapsed live wait.');
