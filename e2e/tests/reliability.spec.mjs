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
