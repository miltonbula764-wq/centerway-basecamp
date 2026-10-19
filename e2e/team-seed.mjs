// Disposable real GoTrue identities only. Passwords never printed or placed in reports.
import fs from 'node:fs';import assert from 'node:assert/strict';import {randomBytes} from 'node:crypto';
const cfg=JSON.parse(fs.readFileSync('e2e/private/public.json'));assert.equal(cfg.url,'http://127.0.0.1:54321');
const password=randomBytes(24).toString('base64url')+'-Aa1!';const users={};
async function call(path,token,body){const r=await fetch(cfg.url+path,{method:'POST',headers:{apikey:cfg.anon,Authorization:`Bearer ${token||cfg.anon}`,'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await r.json();assert.ok(r.ok,`${path}: ${r.status}`);return result;}
for(const name of ['admin','invitee','other','unverified','viewer','secondAdmin']){
 const email=`team-${name.toLowerCase()}@example.invalid`;
 await call('/auth/v1/signup',null,{email,password});const s=await call('/auth/v1/token?grant_type=password',null,{email,password});assert.ok(s.user.email_confirmed_at);users[name]={id:s.user.id,email,password,token:s.access_token};
}
const rpc=(name,token,args)=>call('/rest/v1/rpc/'+name,token,args);
const tenant=await rpc('create_tenant',users.admin.token,{_name:'[SINTÉTICO] Equipa SaaS A',_subject_unit_type:'organization'});
const otherTenant=await rpc('create_tenant',users.other.token,{_name:'[SINTÉTICO] Equipa SaaS B',_subject_unit_type:'organization'});
for(const role of ['viewer'])await rpc('add_tenant_member',users.admin.token,{_tenant_id:tenant,_user_id:users[role].id,_role:role});
// Admin belongs to B too, so browser tests can switch tenant while an A request is pending.
await rpc('add_tenant_member',users.other.token,{_tenant_id:otherTenant,_user_id:users.admin.id,_role:'viewer'});
fs.writeFileSync('e2e/private/team-users.json',JSON.stringify(users));
fs.writeFileSync('e2e/team-fixtures.json',JSON.stringify({tenant,otherTenant,users:Object.fromEntries(Object.entries(users).map(([k,v])=>[k,{id:v.id,email:v.email}]))}));
console.log('Team fixtures: real GoTrue sessions with server-confirmed emails (test-only auto-confirm), two isolated synthetic companies. No email delivery is claimed.');
