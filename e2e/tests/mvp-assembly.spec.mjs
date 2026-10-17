// Assembly smoke only. Does not replace the later complete C01-C10 security campaign.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
test('assembled MVP: actual login, persisted cases, result dossiers and open alternative', async ({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
    const u=new URL(route.request().url());
    if(u.hostname==='fonts.googleapis.com') return route.fulfill({contentType:'text/css',body:''});
    if(['127.0.0.1','localhost'].includes(u.hostname)) return route.continue();
    return route.abort('blockedbyclient');
  });
  await page.goto('/auth');
  await page.getByLabel('Email',{exact:true}).fill(users.admin.email);
  await page.getByLabel('Palavra-passe',{exact:true}).fill(users.admin.password);
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await expect(page).toHaveURL(/\/app(?:$|[/?])/);
  await page.goto('/app/casos');
  await expect(page.getByRole('heading',{name:'Casos · percurso CENTERWAY',exact:true})).toBeVisible();
  for(const name of ['Loja Aurora · investigar','Loja Aurora · aprovar','Loja Aurora · executar','Loja Aurora · em observação','Loja Aurora · resultado atingido','Loja Aurora · objetivo por atingir'])
    await expect(page.getByRole('button').filter({hasText:name})).toBeVisible();
  await page.getByRole('button').filter({hasText:'Loja Aurora · resultado atingido'}).click();
  await expect(page.getByText('Critérios do cenário satisfeitos.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'C09 · Resultados',exact:true}).click();
  await expect(page.getByText('Antes',{exact:true})).toBeVisible();
  await expect(page.getByText('Depois',{exact:true})).toBeVisible();
  await expect(page.getByText(/objetivo: atingido/)).toBeVisible();
  await page.screenshot({path:'logs/mvp-result.png',fullPage:true});
  await page.getByRole('button').filter({hasText:'Loja Aurora · objetivo por atingir'}).click();
  await expect(page.getByText('O caso continua aberto.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'C09 · Resultados',exact:true}).click();
  await expect(page.getByText(/objetivo: não demonstrado/)).toBeVisible();
  await page.screenshot({path:'logs/mvp-open.png',fullPage:true});
  await page.getByRole('button').filter({hasText:'Loja Aurora · aprovar'}).click();
  await expect(page.getByRole('button',{name:'Aprovar este plano como administrador'})).toBeVisible();
  await page.getByRole('button',{name:'C06 · Plano',exact:true}).click();
  await expect(page.getByText('Operador verifica a integração, reativa manualmente e confirma o estado no sistema de origem.',{exact:true})).toBeVisible();
  await page.screenshot({path:'logs/mvp-plan.png',fullPage:true});
  expect(errors).toEqual([]);
});
