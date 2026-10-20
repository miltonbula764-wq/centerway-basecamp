import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const atlas=JSON.parse(fs.readFileSync(new URL('../operational-fixtures.json',import.meta.url)));
const central=JSON.parse(fs.readFileSync(new URL('../followup-fixtures.json',import.meta.url)));
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
const panel=page=>page.getByRole('region',{name:'Revisões programadas',exact:true});
async function login(page,role='admin',tenant=atlas.tenant){
 await page.addInitScript(t=>{if(!localStorage.getItem('centerway.selectedTenant'))localStorage.setItem('centerway.selectedTenant',t);},tenant);
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort();});
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users[role].email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users[role].password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app(?:$|[/?])/);
 if(page.viewportSize().width<768)await page.getByRole('button',{name:'Abrir menu',exact:true}).click();
 await page.getByRole('link',{name:'Acompanhamento',exact:true}).click();
}
test('real admin: bounded monitoring, mobile filters, persisted history and correct closed case link',async({page})=>{
 await page.setViewportSize({width:390,height:844});await login(page);
 const section=panel(page);await expect(section.getByText(/Último ciclo completo:/)).toBeVisible();
 for(let i=0;i<4;i++){
  const response=page.waitForResponse(r=>r.url().endsWith('/rpc/prepare_scheduled_reviews')&&r.request().method()==='POST');
  await section.getByRole('button',{name:'Preparar próximo lote de revisões',exact:true}).click();
  const r=await response;expect(r.status()).toBe(200);expect((await r.json()).status).toBe('completed');
  await expect(section.getByRole('button',{name:'Preparar próximo lote de revisões',exact:true})).toBeEnabled();
 }
 await section.getByLabel('Estado da revisão',{exact:true}).selectOption('closed');await section.getByRole('button',{name:'Filtrar revisões',exact:true}).click();
 const entry=section.getByTestId('scheduled-review');await expect(entry).toHaveCount(1);await expect(entry).toContainText('Caso encerrado');
 await section.getByRole('button',{name:'Atualizar revisões',exact:true}).click();await expect(entry).toHaveCount(1);
 const target=new URL(await entry.getByRole('link',{name:'Consultar registo operacional',exact:true}).getAttribute('href'),'http://127.0.0.1');
 await entry.getByRole('link',{name:'Consultar registo operacional',exact:true}).click();
 await expect(page).toHaveURL(/\/app\/casos/);await expect(page.getByText('Cliente acompanhado',{exact:true}).locator('..').locator('select')).toHaveValue(atlas.customers.find(s=>s.stage==='historical_resolved').subject_id);
 await expect(page.getByLabel('Caso operacional',{exact:true})).toHaveValue(target.searchParams.get('case'));
 const dossier=page.locator('section').filter({has:page.getByRole('heading',{name:'Dossier operacional C05–C10',exact:true})});
 await expect(dossier.getByRole('status')).toContainText('Encerrado com critérios satisfeitos');
});
test('real viewer: no preparation, late monitoring response cannot survive tenant switch or logout',async({page})=>{
 await login(page,'viewer',central.tenant);const section=panel(page);
 await expect(section.getByTestId('scheduled-review').first()).toBeVisible();await expect(section.getByRole('button',{name:'Preparar próximo lote de revisões',exact:true})).toHaveCount(0);
 let release,started;const gate=new Promise(r=>release=r),dispatched=new Promise(r=>started=r);
 await page.route('**/rest/v1/rpc/scheduled_reviews',async route=>{if(route.request().postDataJSON()._tenant_id!==central.tenant)return route.continue();const response=await route.fetch();started();await gate;await route.fulfill({response}).catch(()=>{});});
 await section.getByRole('button',{name:'Atualizar revisões',exact:true}).click();await dispatched;
 await page.getByRole('button',{name:/Central SaaS/}).click();await page.getByRole('menuitem',{name:/Atlas SaaS/}).click();release();
 await expect(page).toHaveURL(/\/app$/);
 await page.getByRole('link',{name:'Acompanhamento',exact:true}).click();
 await expect(page.getByText(/Atlas SaaS.*Estados persistidos/)).toBeVisible();await expect(section.getByText('[SINTÉTICO] Cliente 000',{exact:false})).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys.filter(k=>k[0]==='t').every(k=>k[1]===localStorage.getItem('centerway.selectedTenant')))).toBe(true);
 await page.reload();await expect(page.getByText(/Atlas SaaS.*Estados persistidos/)).toBeVisible();
 await page.getByRole('button',{name:'Terminar sessão',exact:true}).first().click();await expect(page).toHaveURL(/\/auth/);
 await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys.filter(k=>k[0]==='t').length)).toBe(0);
});
