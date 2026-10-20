import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const f=JSON.parse(fs.readFileSync(new URL('../cycle-fixtures.json',import.meta.url)));
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
const dossier=page=>page.locator('section').filter({has:page.getByRole('heading',{name:'Dossier operacional C05–C10',exact:true})});
async function login(page,role='admin'){
 await page.addInitScript(t=>localStorage.setItem('centerway.selectedTenant',t),f.tenant);
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort();});
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users[role].email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users[role].password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app(?:$|[/?])/);
 await page.goto(`/app/casos?tenant=${f.tenant}&subject=${f.subject}&case=${f.case}&kind=operational`);
 await expect(dossier(page).getByRole('heading',{name:/Ciclo atual/})).toBeVisible();
}
async function fill(form,values){for(const [k,v] of Object.entries(values))await form.locator(`[name="${k}"]`).fill(v);}
test('same persisted case: third complete cycle, documented fourth cycle and read-only independent history',async({page})=>{
 await login(page);const d=dossier(page);await expect(d.getByRole('heading',{name:'Ciclo atual · 3',exact:true})).toBeVisible();
 await d.getByRole('button',{name:'Consultar ciclo 1',exact:true}).click();await expect(d.getByRole('heading',{name:'Ciclo histórico · 1',exact:true})).toBeVisible();
 await expect(page.getByRole('form',{name:'C05 · Investigar',exact:true})).toHaveCount(0);await expect(d.getByText(/Consulta histórica/)).toBeVisible();await expect(d.getByText('C09 · Evidência insuficiente',{exact:true})).toBeVisible();
 await d.getByRole('button',{name:'Voltar ao ciclo atual',exact:true}).click();await expect(d.getByRole('heading',{name:'Ciclo atual · 3',exact:true})).toBeVisible();await expect(d.getByText(/Validade da última autorização/)).toHaveCount(0);
 const c05=page.getByRole('form',{name:'C05 · Investigar',exact:true});await c05.getByLabel('Conclusão da investigação',{exact:true}).selectOption('confirmed');await c05.locator(`input[value="${f.proof}"]`).check();await fill(c05,{finding:'[SINTÉTICO] Nova investigação deste ciclo',reference:'urn:cycles:browser:investigation'});await c05.getByRole('button',{name:'Registar investigação',exact:true}).click();
 await expect(d.getByRole('status')).toContainText('Impedimento confirmado');
 const plan=page.getByRole('form',{name:'C06 · Preparar ou rever plano',exact:true});await fill(plan,{action:'[SINTÉTICO] Novo ajuste humano',rationale:'[SINTÉTICO] Novo fundamento',success_conditions:'Objetivo histórico e medições posteriores ao ciclo',limitations:'Sem causalidade automática',reversal:'Revisão humana antes de reverter',reference:'urn:cycles:browser:plan',observation_seconds:'1'});await plan.getByRole('button',{name:'Guardar plano para autorização',exact:true}).click();
 const approve=page.getByRole('form',{name:'C07 · Autorizar plano atual',exact:true});await fill(approve,{valid_until:new Date(Date.now()+3600000).toISOString(),reason:'[SINTÉTICO] Autorização independente do terceiro ciclo',reference:'urn:cycles:browser:approval'});await approve.getByRole('button',{name:'Autorizar plano atual',exact:true}).click();
 const execute=page.getByRole('form',{name:'C07 · Registar execução humana',exact:true});await fill(execute,{receipt:'[SINTÉTICO] Execução humana deste ciclo, sem prova de valor',reference:'urn:cycles:browser:execution'});await execute.getByRole('button',{name:'Registar execução autorizada',exact:true}).click();await expect(d.getByRole('status')).toContainText('Em observação');
 await page.waitForTimeout(1100); // Genuine one-second test window explicitly configured above.
 const observe=page.getByRole('form',{name:'C09 · Comparar nova evidência',exact:true});await observe.getByLabel('Novo pacote C03',{exact:true}).selectOption(f.after_bundle);await observe.getByRole('button',{name:'Comparar com objetivo histórico',exact:true}).click();await expect(d.getByText('C09 · Evidência insuficiente',{exact:true})).toBeVisible();
 const decide=page.getByRole('form',{name:'C10 · Decisão humana documentada',exact:true});await decide.getByLabel('Decisão solicitada',{exact:true}).selectOption('true');await decide.getByLabel('Critérios específicos satisfeitos?',{exact:true}).selectOption('true');await decide.getByLabel('Existe contradição material?',{exact:true}).selectOption('false');await fill(decide,{reason:'[SINTÉTICO] A prova histórica não demonstra este ciclo',reference:'urn:cycles:browser:decision'});await decide.getByRole('button',{name:'Registar decisão de continuidade ou fecho',exact:true}).click();await expect(d.getByRole('status')).toContainText('Caso permanece aberto');
 const start=page.getByRole('form',{name:'Core · Iniciar novo ciclo',exact:true});await fill(start,{reason:'[SINTÉTICO] Decisão humana de continuar com outro ciclo',reference:'urn:cycles:browser:continuation'});await start.getByRole('button',{name:'Iniciar novo ciclo documentado',exact:true}).click();await expect(d.getByRole('heading',{name:'Ciclo atual · 4',exact:true})).toBeVisible();
 await expect(page.getByLabel('Caso operacional',{exact:true})).toHaveValue(f.case);await expect(d.getByText(/Validade da última autorização/)).toHaveCount(0);await expect(d.getByText('C08 · Janela validada pelo servidor',{exact:true})).toHaveCount(0);await expect(page.getByRole('form',{name:'C05 · Investigar',exact:true})).toBeVisible();
 await page.reload();await expect(d.getByRole('heading',{name:'Ciclo atual · 4',exact:true})).toBeVisible();await d.getByRole('button',{name:'Consultar ciclo 3',exact:true}).click();await expect(d.getByRole('heading',{name:'Ciclo histórico · 3',exact:true})).toBeVisible();await expect(page.getByRole('form',{name:'C05 · Investigar',exact:true})).toHaveCount(0);await expect(d.getByText('C09 · Evidência insuficiente',{exact:true})).toBeVisible();
});
test('real viewer cannot act; delayed cycle history cannot cross company switch',async({page})=>{
 await login(page,'viewer');await expect(page.getByRole('form',{name:'Core · Iniciar novo ciclo',exact:true})).toHaveCount(0);await expect(page.getByRole('form',{name:'C05 · Investigar',exact:true})).toHaveCount(0);
 let started,release;const gate=new Promise(r=>release=r),dispatched=new Promise(r=>started=r);
 await page.route('**/rest/v1/rpc/operational_cycle_history',async route=>{const response=await route.fetch();started();await gate;await route.fulfill({response}).catch(()=>{});});
 await dossier(page).getByRole('button',{name:'Consultar ciclo 1',exact:true}).click();await dispatched;
 await page.getByRole('button',{name:/Atlas SaaS/}).click();await page.getByRole('menuitem',{name:/Central SaaS/}).click();release();await expect(page).toHaveURL(/\/app$/);
 await expect(page.getByRole('heading',{name:/Ciclo histórico/})).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys.filter(k=>k[0]==='t').every(k=>k[1]===localStorage.getItem('centerway.selectedTenant')))).toBe(true);
});
