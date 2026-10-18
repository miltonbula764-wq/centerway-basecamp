import { test, expect } from '@playwright/test';
import fs from 'node:fs';
const f=JSON.parse(fs.readFileSync(new URL('../operational-fixtures.json',import.meta.url)));
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
const core=page=>page.locator('section').filter({has:page.getByRole('heading',{name:'Core · Percurso operacional configurável',exact:true})});
const dossier=page=>page.locator('section').filter({has:page.getByRole('heading',{name:'Dossier operacional C05–C10',exact:true})});
async function login(page) {
 await page.addInitScript(tenant=>localStorage.setItem('centerway.selectedTenant',tenant),f.tenant); // Preference only; membership still verified by app + RLS.
 await page.route('**/*',route=>{ const u=new URL(route.request().url()); if(['127.0.0.1','localhost'].includes(u.hostname)) return route.continue(); if(u.hostname==='fonts.googleapis.com') return route.fulfill({contentType:'text/css',body:''}); return route.abort('blockedbyclient'); });
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users.admin.email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users.admin.password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app(?:$|[/?])/);
 await page.goto('/app/casos');
}
async function customer(page,stage) {
 const s=f.customers.find(s=>s.stage===stage);
 await page.getByText('Cliente acompanhado',{exact:true}).locator('..').locator('select').selectOption(s.subject_id);
 return s;
}
async function fill(form,values) {for(const [name,value] of Object.entries(values)) await form.locator(`[name="${name}"]`).fill(value);}
async function observe(page,bundle) {
 const form=page.getByRole('form',{name:'C09 · Comparar nova evidência',exact:true});await form.getByLabel('Novo pacote C03',{exact:true}).selectOption(bundle);await form.getByRole('button',{name:'Comparar com objetivo histórico',exact:true}).click();await expect(dossier(page).getByRole('status')).toContainText('C09 · Resultado registado');
}
async function decide(page,met=true,contradiction=false) {
 const form=page.getByRole('form',{name:'C10 · Decisão humana documentada',exact:true});
 await form.getByLabel('Decisão solicitada',{exact:true}).selectOption('true');await form.getByLabel('Critérios específicos satisfeitos?',{exact:true}).selectOption(String(met));await form.getByLabel('Existe contradição material?',{exact:true}).selectOption(String(contradiction));
 await fill(form,{reason:'[SINTÉTICO] Revisão humana dos critérios e provas deste caso',reference:'urn:atlas:browser:decision'});await form.getByRole('button',{name:'Registar decisão de continuidade ou fecho',exact:true}).click();
}
test('prospective C04→Core→C10: no C02 candidate, valid authorization, real wait and insufficient later proof keeps open',async({page})=>{
 await login(page);const s=await customer(page,'prospective');const panel=core(page);
 await panel.getByLabel('Entrada C04',{exact:true}).selectOption(s.evaluation_id);
 const form=panel.locator('form');await fill(form,{opening_criteria:'[SINTÉTICO] Meta individual não atingida apesar de ausência de deterioração C02',eligibility_reason:'[SINTÉTICO] Administrador confirma elegibilidade deste acompanhamento',eligibility_ref:'urn:atlas:browser:opening',closure_criteria:'[SINTÉTICO] Meta histórica demonstrada com medições posteriores à execução e revisão humana; janela de 1 segundo exclusiva deste teste, insuficiente para duas janelas diárias agora',closure_ref:'urn:atlas:browser:closure'});
 await form.locator('input[type=checkbox]').check();const response=page.waitForResponse(r=>r.url().endsWith('/rpc/open_operational_case')&&r.request().method()==='POST');await form.getByRole('button',{name:'Abrir caso com decisão documentada'}).click();const created=await response;expect(created.status()).toBe(200);const id=await created.json();
 await expect(dossier(page).getByRole('status')).toContainText('C05 · Em investigação');
 const c05=page.getByRole('form',{name:'C05 · Investigar',exact:true});await c05.getByLabel('Conclusão da investigação',{exact:true}).selectOption('hypothesis');await fill(c05,{finding:'[SINTÉTICO] Hipótese ainda sem confirmação',reference:'urn:atlas:browser:hypothesis'});await c05.getByRole('button',{name:'Registar investigação',exact:true}).click();await expect(dossier(page).getByRole('status')).toContainText('C05 · Hipótese');await expect(page.getByRole('form',{name:'C06 · Preparar ou rever plano',exact:true})).toHaveCount(0);
 await c05.getByLabel('Conclusão da investigação',{exact:true}).selectOption('confirmed');await c05.locator(`input[value="${s.proof_id}"]`).check();await fill(c05,{finding:'[SINTÉTICO] Pessoa confirma impedimento com facto C01 referenciado',reference:'urn:atlas:browser:confirmed'});await c05.getByRole('button',{name:'Registar investigação',exact:true}).click();await expect(dossier(page).getByRole('status')).toContainText('Impedimento confirmado');
 const c06=page.getByRole('form',{name:'C06 · Preparar ou rever plano',exact:true});await fill(c06,{action:'[SINTÉTICO] Pessoa ajusta configuração documentada',rationale:'Hipótese revista com prova e confirmação humana',success_conditions:'Medir o objetivo histórico após janela válida',limitations:'Sem execução externa nem prova automática de causalidade',reversal:'Repor configuração apenas após revisão humana',reference:'urn:atlas:browser:plan',observation_seconds:'1'});await c06.getByRole('button',{name:'Guardar plano para autorização',exact:true}).click();await expect(dossier(page).getByRole('status')).toContainText('Plano aguarda autorização');
 const approve=page.getByRole('form',{name:'C07 · Autorizar plano atual',exact:true});await fill(approve,{valid_until:new Date(Date.now()+3600000).toISOString(),reason:'[SINTÉTICO] Autorização explícita deste plano',reference:'urn:atlas:browser:approval'});await approve.getByRole('button',{name:'Autorizar plano atual',exact:true}).click();await expect(dossier(page).getByRole('status')).toContainText('Autorização registada');
 const execute=page.getByRole('form',{name:'C07 · Registar execução humana',exact:true});await fill(execute,{receipt:'[SINTÉTICO] Pessoa declara execução autorizada; não é recuperação de valor',reference:'urn:atlas:browser:receipt'});await execute.getByRole('button',{name:'Registar execução autorizada',exact:true}).click();await expect(dossier(page).getByRole('status')).toContainText('Em observação');
 await page.waitForTimeout(1200); // Actual explicitly configured test window; server remains the authority.
 await observe(page,s.after_bundle_id);await expect(dossier(page).getByText('C09 · Evidência insuficiente',{exact:true})).toBeVisible();await decide(page);await expect(dossier(page).getByRole('status')).toContainText('Caso permanece aberto');
 await page.reload();await customer(page,'prospective');await core(page).getByLabel('Caso operacional',{exact:true}).selectOption(id);await expect(dossier(page).getByRole('status')).toContainText('Caso permanece aberto');await dossier(page).getByText('Histórico imutável e referências',{exact:true}).click();await expect(dossier(page).getByText(/#\d+ · record_execution →/)).toHaveCount(1);await expect(dossier(page).getByRole('alert')).toHaveCount(0);
 await page.screenshot({path:'logs/operational-prospective-open.png',fullPage:true});
});
test('retrospective synthetic C07-C08 fixture: real C09-C10 closes only after goal and human criteria review',async({page})=>{
 await login(page);const s=await customer(page,'historical_resolved');const select=core(page).getByLabel('Caso operacional',{exact:true});await select.selectOption({index:1});await expect(dossier(page).getByText('Histórico sintético retrospectivo: não comprova autorização ou execução passadas.',{exact:true})).toBeVisible();
 await observe(page,s.after_bundle_id);await expect(dossier(page).getByText('C09 · Objetivo atingido',{exact:true})).toBeVisible();await decide(page,true,true);await expect(dossier(page).getByRole('status')).toContainText('Caso permanece aberto');
 await observe(page,s.after_bundle_id);await decide(page);await expect(dossier(page).getByRole('status')).toContainText('Encerrado com critérios satisfeitos');await page.screenshot({path:'logs/operational-resolved.png',fullPage:true});
});
test('independent incomplete C04 stays visible and an unmet historical goal cannot close',async({page})=>{
 await login(page);const s=await customer(page,'historical_unmet');await core(page).getByLabel('Entrada C04',{exact:true}).selectOption(f.incompleteEvaluation);await expect(core(page).getByText(/Pendência C04:/)).toBeVisible();await expect(core(page).getByRole('button',{name:'Abrir caso com decisão documentada'})).toHaveCount(0);
 await core(page).getByLabel('Caso operacional',{exact:true}).selectOption({index:1});await observe(page,s.after_bundle_id);await expect(dossier(page).getByText('C09 · Objetivo não atingido',{exact:true})).toBeVisible();await decide(page);await expect(dossier(page).getByRole('status')).toContainText('Caso permanece aberto');
});
