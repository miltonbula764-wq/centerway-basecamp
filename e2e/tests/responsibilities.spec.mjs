import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const f=JSON.parse(fs.readFileSync(new URL('../responsibility-fixtures.json',import.meta.url)));
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
async function login(page,role='admin'){
 await page.addInitScript(t=>localStorage.setItem('centerway.selectedTenant',t),f.tenant);
 await page.route('**/*',route=>{const u=new URL(route.request().url());if(['127.0.0.1','localhost'].includes(u.hostname))return route.continue();if(u.hostname==='fonts.googleapis.com')return route.fulfill({contentType:'text/css',body:''});return route.abort();});
 await page.goto('/auth');await page.getByLabel('Email',{exact:true}).fill(users[role].email);await page.getByLabel('Palavra-passe',{exact:true}).fill(users[role].password);await page.getByRole('button',{name:'Entrar',exact:true}).click();await expect(page).toHaveURL(/\/app(?:$|[/?])/);
}
const resp=page=>page.getByRole('region',{name:'Responsável do caso',exact:true});
test('real admin assignment, immutable history, operator inbox/my-work, read persistence and exact case navigation',async({page,browser})=>{
 await login(page);await page.goto(`/app/casos?tenant=${f.tenant}&subject=${f.subject}&case=${f.case}&kind=operational`);
 const form=page.getByRole('form',{name:'Gerir responsável',exact:true});await expect(form).toBeVisible();
 await form.getByLabel('Responsável proposto',{exact:true}).selectOption(f.admin);await form.getByLabel('Fundamento da atribuição ou remoção').fill('[SINTÉTICO] Substituição humana pelo browser');await form.getByLabel('Referência da atribuição (HTTPS ou URN)').fill('urn:responsibilities:browser:admin');await form.getByRole('button',{name:'Guardar responsabilidade documentada'}).click();await expect(resp(page).getByText('Responsabilidade registada.',{exact:true})).toBeVisible();
 await form.getByLabel('Responsável proposto',{exact:true}).selectOption(f.operator);await form.getByLabel('Fundamento da atribuição ou remoção').fill('[SINTÉTICO] Atribuição ao operador pelo browser');await form.getByLabel('Referência da atribuição (HTTPS ou URN)').fill('urn:responsibilities:browser:operator');await form.getByRole('button',{name:'Guardar responsabilidade documentada'}).click();await expect(resp(page).getByText(`Responsável: ${f.operator}`,{exact:true})).toBeVisible();
 await resp(page).getByText('Histórico de responsabilidades',{exact:true}).click();await expect(resp(page).getByText('[SINTÉTICO] Atribuição ao operador pelo browser',{exact:true})).toBeVisible();
 const ctx=await browser.newContext();const p=await ctx.newPage();await login(p,'operator');await p.goto('/app/acompanhamento');
 const work=p.getByRole('region',{name:'As minhas pendências',exact:true});await expect(work.getByTestId('my-work').filter({hasText:f.case})).toBeVisible();
 const inbox=p.getByRole('region',{name:'Caixa de notificações',exact:true});const notice=inbox.getByTestId('notification').filter({hasText:f.case}).first();await expect(notice).toBeVisible();await notice.getByRole('button',{name:'Marcar como lida',exact:true}).click();await expect(notice.getByRole('heading')).toContainText('Lida');await p.reload();await expect(inbox.getByTestId('notification').first().getByRole('heading')).toContainText('Lida');
 await inbox.getByTestId('notification').first().getByRole('link',{name:'Caso da notificação',exact:true}).click();await expect(p.getByLabel('Caso operacional',{exact:true})).toHaveValue(f.case);await expect(p.getByRole('form',{name:'Gerir responsável',exact:true})).toHaveCount(0);await ctx.close();
});
test('private inbox late response cannot survive company change or logout',async({page})=>{
 await login(page,'operator');await page.goto('/app/acompanhamento');await expect(page.getByRole('region',{name:'Caixa de notificações'}).getByTestId('notification').first()).toBeVisible();
 let started,release;const gate=new Promise(r=>release=r),dispatched=new Promise(r=>started=r);
 await page.route('**/rest/v1/rpc/notification_inbox',async route=>{const response=await route.fetch();started();await gate;await route.fulfill({response}).catch(()=>{});});
 await page.getByRole('button',{name:'Atualizar notificações',exact:true}).click();await dispatched;
 await page.getByRole('button',{name:/Atlas SaaS/}).click();await page.getByRole('menuitem',{name:/Central SaaS/}).click();release();await expect(page).toHaveURL(/\/app$/);await expect(page.getByTestId('notification')).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>window.__CW_E2E_STATE__().keys.filter(k=>k[0]==='t').every(k=>k[1]===localStorage.getItem('centerway.selectedTenant')))).toBe(true);
 await page.getByRole('button',{name:'Terminar sessão',exact:true}).click();await expect(page).toHaveURL(/\/auth/);await expect(page.getByText('Notificações internas',{exact:true})).toHaveCount(0);
});
