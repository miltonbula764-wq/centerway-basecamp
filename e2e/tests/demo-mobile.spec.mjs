// Local test TLS + Chromium Android emulation. Not a real Codespaces or physical Android certification.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
const f=JSON.parse(fs.readFileSync(new URL('../operational-fixtures.json',import.meta.url)));
const config=JSON.parse(fs.readFileSync(new URL('../private/public.json',import.meta.url)));
const origin=process.env.CW_DEMO_BASE_URL;
test.skip(!origin, 'Local HTTPS demo suite only; not a remote Codespaces check.');
async function login(page){
 await page.addInitScript(id=>localStorage.setItem('centerway.selectedTenant',id),f.tenant);
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users.admin.email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users.admin.password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app(?:$|[/?])/);
}
test('mobile HTTPS: same-origin auth/RPC, persisted session, navigation and private files blocked',async({page,request})=>{
 const unexpected=[];let api=0;const sockets=[];
 page.on('request',r=>{const u=new URL(r.url());if(/\/(auth|rest)\/v1/.test(u.pathname)){api++;if(u.origin!==origin)unexpected.push(u.origin);}});
 page.on('websocket',s=>sockets.push(s.url()));
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin===origin)return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort('blockedbyclient');});
 await login(page);await page.goto('/app/casos');await page.getByText('Cliente acompanhado',{exact:true}).locator('..').locator('select').selectOption(f.customers[0].subject_id);
 await expect(page.getByRole('heading',{name:'Core · Percurso operacional configurável',exact:true})).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.reload();await expect(page).toHaveURL(/\/app\/casos/);await expect(page.getByRole('heading',{name:'Casos · percurso CENTERWAY',exact:true})).toBeVisible();
 for(const path of ['/app/clientes','/app/perfil','/app/dados','/app/casos']){await page.goto(path);await expect(page).toHaveURL(new RegExp(path));}
 await expect.poll(()=>api).toBeGreaterThan(5);expect(unexpected).toEqual([]);
 expect(sockets.length).toBeGreaterThan(0);for(const url of sockets){expect(new URL(url).hostname).toBe('demo.centerway.test');expect(new URL(url).protocol).toBe('wss:');}
 // No credentials, migration files, config secrets or arbitrary workspace files over Vite.
 for(const path of ['/e2e/private/mvp-users.json','/e2e/private/auth.env','/.env.local','/drizzle/migrations/0014_configurable_case_journey.sql','/@fs'+process.cwd().replace(/\/e2e$/,'')+'/e2e/private/mvp-users.json']){
  const response=await request.get(origin+path);expect([403,404]).toContain(response.status());
 }
 const signup=await request.post(origin+'/auth/v1/signup',{headers:{apikey:config.anon},data:{email:'synthetic-disabled@example.invalid',password:'NotAnActualAccount-123!'}});expect(signup.ok()).toBe(false);
 await page.screenshot({path:'logs/demo-mobile-session.png',fullPage:true});
});
test('HTTPS API: real JWT, viewer permission and tenant isolation without hosted credentials',async({request})=>{
 async function token(role){const r=await request.post(origin+'/auth/v1/token?grant_type=password',{headers:{apikey:config.anon},data:{email:users[role].email,password:users[role].password}});expect(r.ok()).toBe(true);return(await r.json()).access_token;}
 const admin=await token('admin'),viewer=await token('viewer');const headers=t=>({apikey:config.anon,Authorization:'Bearer '+t});
 const created=await request.post(origin+'/rest/v1/rpc/create_tenant',{headers:headers(viewer),data:{_name:'[SINTÉTICO] Privada de teste de isolamento',_subject_unit_type:'organization'}});expect(created.ok()).toBe(true);const tenant=await created.json();
 const subject=await request.post(origin+'/rest/v1/subjects',{headers:{...headers(viewer),Prefer:'return=representation'},data:{tenant_id:tenant,external_ref:'synthetic-private-only',display_name:'[SINTÉTICO] Isolamento'}});expect(subject.ok()).toBe(true);
 const hidden=await request.get(origin+'/rest/v1/subjects?tenant_id=eq.'+tenant,{headers:headers(admin)});expect(await hidden.json()).toEqual([]);
 const denied=await request.post(origin+'/rest/v1/rpc/open_operational_case',{headers:headers(viewer),data:{_tenant_id:f.tenant,_evaluation_id:f.customers[0].evaluation_id,_operation_id:crypto.randomUUID(),_definition:{}}});expect(denied.status()).toBe(403);
 const anonymous=await request.get(origin+'/rest/v1/cw_operational_cases',{headers:{apikey:config.anon}});expect(anonymous.ok()).toBe(false);
 const invalid=await request.get(origin+'/rest/v1/subjects',{headers:headers(admin.slice(0,-6)+'badbad')});expect(invalid.status()).toBe(401);
});
