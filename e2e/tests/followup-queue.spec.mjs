import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const f=JSON.parse(fs.readFileSync(new URL('../followup-fixtures.json',import.meta.url)));
const atlas=JSON.parse(fs.readFileSync(new URL('../operational-fixtures.json',import.meta.url)));
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
async function login(page,role='admin',tenant=f.tenant){
 await page.addInitScript(t=>{if(!localStorage.getItem('centerway.selectedTenant'))localStorage.setItem('centerway.selectedTenant',t);},tenant);
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort();});
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users[role].email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users[role].password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app(?:$|[/?])/);
 await page.getByRole('link',{name:'Acompanhamento',exact:true}).click();await expect(page.getByRole('heading',{name:'Central de acompanhamento'})).toBeVisible();
}
async function filter(page,client,indicator='',category=''){
 await page.getByLabel('Cliente',{exact:true}).fill(client);await page.getByLabel('Indicador',{exact:true}).fill(indicator);await page.getByLabel('Estado',{exact:true}).selectOption(category);await page.getByRole('button',{name:'Filtrar fila',exact:true}).click();
}
test('queue: real auth, independent C04 states, pagination and client beyond the old 100-row list',async({page})=>{
 await login(page);const rows=page.getByTestId('queue-entry');await expect(rows).toHaveCount(25);
 const first=await rows.first().getAttribute('data-entry-key');await page.getByRole('button',{name:'Página seguinte',exact:true}).click();await expect(rows.first()).not.toHaveAttribute('data-entry-key',first);
 await page.getByRole('button',{name:'Página anterior',exact:true}).click();await expect(rows.first()).toHaveAttribute('data-entry-key',first);
 await filter(page,'queue-000');await expect(rows).toHaveCount(3);
 await expect(rows.filter({hasText:'Contradição identificada'})).toHaveCount(1);await expect(rows.filter({hasText:'Avaliação disponível para revisão'})).toHaveCount(1);await expect(rows.filter({hasText:'Informação pendente'})).toHaveCount(1);
 const entry=rows.filter({has:page.getByRole('heading',{name:/independent_minutes/})});await entry.getByRole('link',{name:'Abrir objetivo e avaliação'}).click();await expect(page.getByLabel('Entrada C04',{exact:true})).toHaveValue(f.evaluations.independent_minutes);
 await expect(page.getByText('Cliente acompanhado',{exact:true}).locator('..').locator('select')).toHaveValue(f.customer.id);
 await page.getByRole('link',{name:'Acompanhamento',exact:true}).click();await filter(page,'queue-101','independent');await expect(rows).toHaveCount(1);
 const last=f.subjects.find(s=>s.external_ref==='queue-101');await rows.getByRole('link',{name:'Abrir objetivo e avaliação'}).click();await expect(page.getByText('Cliente acompanhado',{exact:true}).locator('..').locator('select')).toHaveValue(last.id);
 await page.getByRole('link',{name:'Acompanhamento',exact:true}).click();await filter(page,'queue-101','independent');await expect(rows).toHaveCount(1);await rows.getByRole('link',{name:'Abrir cliente',exact:true}).click();await expect(page).toHaveURL(new RegExp('/app/clientes/'+last.id));await expect(page.getByText(last.display_name,{exact:true}).first()).toBeVisible();
});
test('viewer queue is read-only; exact case links validate tenant, client and identity',async({page})=>{
 await login(page,'viewer',atlas.tenant);await filter(page,'atlas-historical_resolved');
 const row=page.getByTestId('queue-entry').filter({has:page.getByRole('link',{name:'Abrir caso',exact:true})});await expect(row).toHaveCount(1);
 const href=await row.getByRole('link',{name:'Abrir caso',exact:true}).getAttribute('href');const target=new URL(href,'http://127.0.0.1:5173');
 await row.getByRole('link',{name:'Abrir caso',exact:true}).click();await expect(page.getByLabel('Caso operacional',{exact:true})).toHaveValue(target.searchParams.get('case'));
 await expect(page.getByRole('heading',{name:'Dossier operacional C05–C10'})).toBeVisible();await expect(page.getByRole('button',{name:'Comparar com objetivo histórico'})).toHaveCount(0);
 const wrongSubject=atlas.customers.find(s=>s.stage==='prospective').subject_id;target.searchParams.set('subject',wrongSubject);target.searchParams.delete('evaluation');await page.goto(target.pathname+target.search);await expect(page.getByText('Caso não encontrado para este cliente e empresa.',{exact:true})).toBeVisible();await expect(page.getByRole('heading',{name:'Dossier operacional C05–C10'})).toHaveCount(0);
 target.searchParams.set('tenant',f.tenant);await page.goto(target.pathname+target.search);await expect(page.getByText(/A ligação pertence a outra empresa/)).toBeVisible();
});
test('queue refresh and delayed request cannot cross an actual tenant switch',async({page})=>{
 await login(page);await filter(page,'queue-000');await expect(page.getByTestId('queue-entry')).toHaveCount(3);
 let release;const gate=new Promise(resolve=>{release=resolve;});let captured;const started=new Promise(resolve=>{captured=resolve;});
 await page.route('**/rest/v1/rpc/core_followup_queue',async route=>{
  const data=route.request().postDataJSON();if(data._tenant_id!==f.tenant)return route.continue();
  const response=await route.fetch();captured();await gate;await route.fulfill({response}).catch(()=>{});
 });
 await page.getByRole('button',{name:'Atualizar fila',exact:true}).click();await started;
 await page.getByRole('button',{name:/Central SaaS/}).click();await page.getByRole('menuitem',{name:/Atlas SaaS/}).click();
 await page.getByRole('link',{name:'Acompanhamento',exact:true}).click();await expect(page.getByText(/Atlas SaaS · SINTÉTICO operacional · Estados persistidos/)).toBeVisible();release();
 await expect(page.getByTestId('queue-entry').filter({hasText:'Cliente 000'})).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys.filter(k=>k[0]==='t').every(k=>k[1]===localStorage.getItem('centerway.selectedTenant')))).toBe(true);
 await page.screenshot({path:'logs/followup-queue.png',fullPage:true});
});
