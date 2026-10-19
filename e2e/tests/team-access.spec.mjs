import {test,expect} from '@playwright/test';import fs from 'node:fs';
const f=JSON.parse(fs.readFileSync(new URL('../team-fixtures.json',import.meta.url)));
const users=JSON.parse(fs.readFileSync(new URL('../private/team-users.json',import.meta.url)));
// Invitation bearer values are never deliberately captured in screenshots/traces/videos.
test.use({screenshot:'off',trace:'off',video:'off'});
async function isolate(page){await page.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort();});}
async function credentials(page,role){await page.getByLabel('Email',{exact:true}).fill(users[role].email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users[role].password);await page.getByRole('button',{name:'Entrar',exact:true}).click();}
async function login(page,role='admin'){
 await isolate(page);await page.addInitScript(t=>{if(!localStorage.getItem('centerway.selectedTenant'))localStorage.setItem('centerway.selectedTenant',t);},f.tenant);
 await page.goto('/auth');await credentials(page,role);await expect(page).toHaveURL(/\/app(?:$|[/?])/);await page.goto('/app/configuracoes');await expect(page.getByRole('heading',{name:'Configurações',exact:true})).toBeVisible();
}
async function create(page,email,role='operator'){
 const form=page.getByRole('form',{name:'Convidar colaborador'});await form.getByLabel('Email autorizado',{exact:true}).fill(email);await form.getByLabel('Papel proposto',{exact:true}).selectOption(role);
 await form.getByLabel('Válido até',{exact:true}).fill(new Date(Date.now()+3600000).toISOString().slice(0,16));
 const done=page.waitForResponse(r=>r.url().endsWith('/rpc/create_tenant_invitation')&&r.request().method()==='POST');await form.getByRole('button',{name:'Criar convite',exact:true}).click();const response=await done;expect(response.status()).toBe(200);const result=await response.json();expect(typeof result.token).toBe('string');return result;
}
const member=(page,email)=>page.getByTestId('team-member').filter({hasText:email});
test('real team journey: invitation, verified account, role enforcement, role update, removal and non-reuse',async({page,browser})=>{
 await login(page);const invite=await create(page,users.invitee.email);
 await expect(page.getByRole('status')).toContainText('Não foi enviado email');
 await page.context().grantPermissions(['clipboard-read','clipboard-write']);await page.getByRole('button',{name:'Copiar ligação',exact:true}).click();
 const copied=await page.evaluate(()=>navigator.clipboard.readText());expect(copied===`http://127.0.0.1:5173/convite#token=${invite.token}`).toBe(true);
 const context=await browser.newContext();const recipient=await context.newPage();await isolate(recipient);
 await recipient.goto(copied);await expect(recipient).toHaveURL(/\/convite$/);await credentials(recipient,'invitee');await expect(recipient.getByRole('heading',{name:'[SINTÉTICO] Equipa SaaS A',exact:true})).toBeVisible();
 await recipient.getByRole('button',{name:'Aceitar convite',exact:true}).click();await expect(recipient).toHaveURL(/\/app\/configuracoes$/);
 await expect(recipient.getByRole('form',{name:'Convidar colaborador'})).toHaveCount(0);await expect(recipient.getByRole('button',{name:'Remover membro'})).toHaveCount(0);await expect(recipient.getByText(users.admin.email,{exact:true})).toHaveCount(0);
 await recipient.reload();await expect(recipient.getByText('Operador',{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:'Atualizar equipa',exact:true}).click();await expect(member(page,users.invitee.email)).toBeVisible();
 await page.getByLabel(`Papel de ${users.invitee.email}`,{exact:true}).selectOption('viewer');await expect(page.getByRole('status')).toContainText('Papel atualizado');
 await recipient.reload();await expect(recipient.getByText('Leitor',{exact:true}).first()).toBeVisible();
 await page.getByLabel(`Papel de ${users.admin.email}`,{exact:true}).selectOption('viewer');await expect(page.getByRole('alert')).toContainText('último administrador');await expect(page.getByLabel(`Papel de ${users.admin.email}`,{exact:true})).toHaveValue('admin');
 await member(page,users.invitee.email).getByRole('button',{name:'Remover membro',exact:true}).click();await page.getByRole('button',{name:'Cancelar',exact:true}).click();await expect(member(page,users.invitee.email)).toBeVisible();
 await member(page,users.invitee.email).getByRole('button',{name:'Remover membro',exact:true}).click();await page.getByRole('button',{name:'Confirmar remoção',exact:true}).click();await expect(member(page,users.invitee.email)).toHaveCount(0);
 await recipient.reload();await expect(recipient).toHaveURL(/\/onboarding$/);
 await recipient.goto(copied);await expect(recipient.getByRole('alert')).toContainText('Convite indisponível');await expect(recipient.getByRole('button',{name:'Aceitar convite'})).toHaveCount(0);
 await context.close();
});
test('revoked invite and another verified email cannot inspect or accept the company invitation',async({page,browser})=>{
 await login(page);const invite=await create(page,users.secondAdmin.email,'viewer');
 const context=await browser.newContext();const recipient=await context.newPage();await isolate(recipient);const url=`http://127.0.0.1:5173/convite#token=${invite.token}`;
 await recipient.goto(url);await credentials(recipient,'other');await expect(recipient.getByRole('alert')).toContainText('Convite indisponível');await expect(recipient.getByRole('heading',{name:'[SINTÉTICO] Equipa SaaS A',exact:true})).toHaveCount(0);
 const row=page.getByTestId('team-invite').filter({hasText:users.secondAdmin.email}).filter({hasText:'Pendente'});await row.getByRole('button',{name:'Revogar convite',exact:true}).click();await expect(page.getByRole('status')).toContainText('Convite revogado');
 await recipient.getByRole('button',{name:'Utilizar outra conta',exact:true}).click();await credentials(recipient,'secondAdmin');await expect(recipient.getByRole('alert')).toContainText('Convite indisponível');await expect(recipient.getByRole('button',{name:'Aceitar convite'})).toHaveCount(0);
 await context.close();
});
test('team response pending at tenant switch never exposes an A invite or private members in B; logout clears cache',async({page})=>{
 await login(page);const form=page.getByRole('form',{name:'Convidar colaborador'});
 let release,started;const gate=new Promise(r=>{release=r;});const captured=new Promise(r=>{started=r;});
 await page.route('**/rest/v1/rpc/create_tenant_invitation',async route=>{const response=await route.fetch();started();await gate;await route.fulfill({response}).catch(()=>{});});
 await form.getByLabel('Email autorizado',{exact:true}).fill(users.invitee.email);await form.getByLabel('Válido até',{exact:true}).fill(new Date(Date.now()+3600000).toISOString().slice(0,16));await form.getByRole('button',{name:'Criar convite',exact:true}).click();await captured;
 await page.getByRole('button',{name:/Equipa SaaS A/}).click();await page.getByRole('menuitem',{name:/Equipa SaaS B/}).click();release();await page.getByRole('link',{name:'Configurações',exact:true}).click();
 await expect(page.getByText('[SINTÉTICO] Equipa SaaS B',{exact:true}).first()).toBeVisible();await expect(page.getByLabel('Ligação de convite')).toHaveCount(0);await expect(page.getByRole('form',{name:'Convidar colaborador'})).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys.filter(k=>k[0]==='t').every(k=>k[1]===localStorage.getItem('centerway.selectedTenant')))).toBe(true);
 await page.reload();await expect(page.getByText('[SINTÉTICO] Equipa SaaS B',{exact:true}).first()).toBeVisible();
 await page.getByRole('button',{name:'Terminar sessão',exact:true}).first().click();await expect(page).toHaveURL(/\/auth/);await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys.filter(k=>k[0]==='t').length)).toBe(0);
});
