import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const f=JSON.parse(fs.readFileSync(new URL('../operational-fixtures.json',import.meta.url)));
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
test('CSV committed but response lost: uncertainty is explicit and retry reuses observation keys',async({page})=>{
 await page.addInitScript(t=>localStorage.setItem('centerway.selectedTenant',t),f.tenant);
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort();});
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users.admin.email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users.admin.password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app/);await page.goto('/app/dados');
 await page.getByLabel('Fonte',{exact:true}).fill('synthetic-recovery-browser');const now=new Date();const start=new Date(+now-86400000);await page.getByLabel('Cobertura — início (UTC)',{exact:true}).fill(start.toISOString().slice(0,16));await page.getByLabel('Cobertura — fim (UTC, exclusivo)',{exact:true}).fill(now.toISOString().slice(0,16));await page.getByRole('checkbox').check();
 const observed=new Date(+now-3600000).toISOString();const csv=`subject_external_ref,indicator_key,observed_at,value_numeric,unit,idempotency_key\natlas-prospective,cycle_minutes,${observed},50,min,${crypto.randomUUID()}`;
 await page.getByLabel('Ficheiro CSV',{exact:true}).setInputFiles({name:'synthetic-recovery.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
 let dropped=false;await page.route('**/rest/v1/rpc/import_observations',async route=>{if(dropped)return route.continue();const response=await route.fetch();expect((await response.json()).status).toBe('completed');dropped=true;await route.abort('connectionreset');});
 await page.getByRole('button',{name:'Confirmar importação de 1 linhas',exact:true}).click();await expect(page.getByRole('alert')).toContainText('Não foi possível confirmar o resultado da importação');await expect(page.getByRole('alert')).not.toContainText('Nada foi gravado');
 await page.getByRole('button',{name:'Confirmar importação de 1 linhas',exact:true}).click();await expect(page.getByRole('status').filter({hasText:'Lote concluído'})).toContainText('0 novas observações · 1 repetidas');
});

test('real logout: revoked Auth session is rejected, protected navigation and caches stay cleared',async({page})=>{
 const cfg=JSON.parse(fs.readFileSync(new URL('../private/public.json',import.meta.url)));
 await page.addInitScript(t=>localStorage.setItem('centerway.selectedTenant',t),f.tenant);
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort();});
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users.viewer.email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users.viewer.password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app/);
 // Keep the synthetic token only in process memory. Never log it or attach traces.
 const token=await page.evaluate(()=>{for(const value of Object.values(localStorage)){try{const session=JSON.parse(value);if(session?.access_token)return session.access_token;}catch{}}return null;});expect(token).toBeTruthy();
 const headers={apikey:cfg.anon,Authorization:'Bearer '+token,'X-Supabase-Api-Version':'2024-01-01'};
 expect((await page.request.get(cfg.url+'/auth/v1/user',{headers})).status()).toBe(200);
 const logout=page.waitForResponse(r=>new URL(r.url()).pathname==='/auth/v1/logout'&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Terminar sessão',exact:true}).click();expect((await logout).ok()).toBe(true);
 await expect(page).toHaveURL(/\/auth/);await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys)).toEqual([]);
 // A late request with the now-revoked session must fail closed in GoTrue.
 const rejected=await page.request.get(cfg.url+'/auth/v1/user',{headers});
 expect(rejected.status()).toBe(403);expect((await rejected.json()).code).toBe('session_not_found');
 // PostgREST denies anonymous late requests with 401 (not a failed logout).
 const anonymous=await page.request.post(cfg.url+'/rest/v1/rpc/operational_onboarding',{headers:{apikey:cfg.anon,Authorization:'Bearer '+cfg.anon},data:{_tenant_id:f.tenant}});
 expect(anonymous.status()).toBe(401);expect((await anonymous.json()).tenant_id).toBeUndefined();
 await page.goto('/app/casos');await expect(page).toHaveURL(/\/auth/);await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys)).toEqual([]);
});
