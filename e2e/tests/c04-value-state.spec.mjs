import { test, expect } from '@playwright/test';
import fs from 'node:fs';
const users=JSON.parse(fs.readFileSync(new URL('../private/mvp-users.json',import.meta.url)));
const fixture=JSON.parse(fs.readFileSync(new URL('../mvp-fixtures.json',import.meta.url)));
const subject=fixture.cases.find(c=>c.stage==='investigation');
test('C04: real configuration, persisted evaluation, revision and independent historical results', async ({page})=>{
  await page.route('**/*',route=>{
    const u=new URL(route.request().url());
    if(['127.0.0.1','localhost'].includes(u.hostname)) return route.continue();
    if(u.hostname==='fonts.googleapis.com') return route.fulfill({contentType:'text/css',body:''});
    return route.abort('blockedbyclient');
  });
  await page.goto('/auth');
  await page.getByLabel('Email',{exact:true}).fill(users.admin.email);
  await page.getByLabel('Palavra-passe',{exact:true}).fill(users.admin.password);
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await expect(page).toHaveURL(/\/app(?:$|[/?])/);
  await page.goto('/app/casos');
  await page.getByText('Cliente acompanhado',{exact:true}).locator('..').locator('select').selectOption(subject.subject_id);
  const panel=page.locator('section').filter({has:page.getByRole('heading',{name:'C04 · Value State configurável',exact:true})});
  await panel.getByRole('button',{name:'Registar informação conhecida',exact:true}).click();
  await panel.getByLabel('Perfil histórico',{exact:true}).selectOption(fixture.profile);
  await panel.getByLabel('Indicador outcome',{exact:true}).selectOption('report_hours');
  for(const [label,value] of [
    ['Promessa documentada da SaaS','SYNTHETIC: reporting automation'],['Referência da promessa','synthetic:promise'],
    ['Capacidade permitida pelo plano contratado','SYNTHETIC: reporting included'],['Referência do plano','synthetic:plan'],
    ['Objetivo específico do cliente','SYNTHETIC: documented independent target'],['Referência da confirmação do objetivo','synthetic:customer'],
    ['Referência da revisão documental humana','synthetic:review'],['Unidade (igual ao perfil)','h/semana'],
    ['Fonte exata das medições','synthetic-flowreports'],['Meta numérica','12'],
    ['Quantidade de janelas C02 atuais a exigir (1–100)','2'],['Início admissível da observação (ISO com fuso)','2020-01-01T00:00:00Z'],['Prazo do objetivo (ISO com fuso)','2021-01-01T00:00:00Z'],
  ]) await panel.getByLabel(label,{exact:true}).fill(value);
  await panel.getByLabel('Revisão documental humana',{exact:true}).selectOption('compatible');
  await panel.getByLabel('Agregação (igual ao perfil C02)',{exact:true}).selectOption('mean');
  await panel.getByLabel('Comparação de cada janela com a meta',{exact:true}).selectOption('lte');
  await panel.getByRole('button',{name:'Guardar nova versão',exact:true}).click();
  await expect(panel.getByText('Consultar definição v1',{exact:true})).toBeVisible();
  await panel.getByLabel('Pacote C03 persistido',{exact:true}).selectOption(subject.bundle_id);
  await panel.getByRole('button',{name:'Avaliar indicador no servidor',exact:true}).click();
  await expect(panel.getByText('Objetivo atingido · report_hours',{exact:true})).toBeVisible();
  await page.reload();
  await page.getByText('Cliente acompanhado',{exact:true}).locator('..').locator('select').selectOption(subject.subject_id);
  await expect(panel.getByText('Objetivo atingido · report_hours',{exact:true})).toBeVisible();
  const version=panel.getByLabel('Configuração histórica (até 100)',{exact:true});
  await version.selectOption({label:await version.locator('option').nth(1).innerText()});
  await panel.getByRole('button',{name:'Criar revisão desta configuração',exact:true}).click();
  await panel.getByLabel('Meta numérica',{exact:true}).fill('5');
  await panel.getByRole('button',{name:'Guardar nova versão',exact:true}).click();
  await expect(panel.getByText('Consultar definição v2',{exact:true})).toBeVisible();
  await panel.getByLabel('Pacote C03 persistido',{exact:true}).selectOption(subject.bundle_id);
  await panel.getByRole('button',{name:'Avaliar indicador no servidor',exact:true}).click();
  await expect(panel.getByText('Objetivo não atingido · report_hours',{exact:true})).toBeVisible();
  await version.selectOption('');
  await expect(panel.getByText('Objetivo atingido · report_hours',{exact:true})).toBeVisible();
  await expect(panel.getByText('Objetivo não atingido · report_hours',{exact:true})).toBeVisible();
  await expect(panel.locator('[role=alert]')).toHaveCount(0);
});
