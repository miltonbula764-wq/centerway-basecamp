import { test, expect } from '@playwright/test';
import fs from 'node:fs';
const fixture = JSON.parse(fs.readFileSync(new URL('../fixtures.json', import.meta.url)));
const users = JSON.parse(fs.readFileSync(new URL('../private/users.json', import.meta.url)));
const buildPath = '**/rest/v1/rpc/build_evidence_bundle';
const rpc = (response) => new URL(response.url()).pathname === '/rest/v1/rpc/build_evidence_bundle';
const evidence = (page) => page.locator('section').filter({ has: page.getByRole('heading', { name: 'Pacote de evidência (C03)', exact: true }) });
const button = (page) => page.getByRole('button', { name: /Montar pacote/ });
const select = (page) => page.getByRole('combobox', { name: 'Análise', exact: true });
const defer = () => { let release; const promise = new Promise(r => { release = r; }); return { promise, release }; };

async function login(page, role = 'admin') {
  await page.goto('/auth');
  await page.getByLabel('Email', { exact: true }).fill(users[role].email);
  await page.getByLabel('Palavra-passe', { exact: true }).fill(users[role].password);
  const signedIn = page.waitForResponse(r => r.url().includes('/auth/v1/token?grant_type=password') && r.status() === 200);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await signedIn;
  await expect(page).toHaveURL(/\/app(?:$|[/?])/);
  await page.waitForFunction(() => typeof window.__CW_E2E_STATE__ === 'function');
}
async function detail(page, customer = fixture.customerA) {
  await page.goto('/app/clientes/' + customer.id);
  await expect(page.getByRole('heading', { name: customer.name, exact: true })).toBeVisible();
  await expect(select(page)).toHaveValue(customer.primary);
}
async function started(page, run) {
  await page.waitForFunction(run => window.__CW_E2E_STATE__().events.some(e => e.run === run && e.status === 'pending'), run);
  return page.evaluate(run => window.__CW_E2E_STATE__().events.filter(e => e.run === run && e.status === 'pending').at(-1).id, run);
}
async function settled(page, id, status = 'success') {
  // QueryClient dispatches terminal state after onSuccess/onError has completed.
  await page.waitForFunction(({id, status}) => window.__CW_E2E_STATE__().events.some(e => e.id === id && e.status === status), {id, status});
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
function holdBuilds(page) {
  const calls = [];
  const gates = [defer(), defer()];
  const done = [defer(), defer()];
  const install = page.route(buildPath, async route => {
    const index = calls.length;
    calls.push(route.request().postDataJSON());
    try {
      await gates[index].promise;
      const response = await route.fetch(); // Real JWT, RLS and RPC, unchanged request body.
      await route.fulfill({ response });
    } finally { done[index].release(); }
  });
  return { calls, gates, done, install };
}

test.beforeEach(async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.__cwErrors = errors;
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname === 'fonts.googleapis.com') return route.fulfill({ contentType: 'text/css', body: '' });
    if (url.hostname === '127.0.0.1' || url.hostname === 'localhost') return route.continue();
    throw new Error('Unexpected external browser request: ' + url.origin);
  });
});
test.afterEach(async ({ page }, info) => {
  await info.attach('javascript-errors', { body: JSON.stringify(page.__cwErrors), contentType: 'application/json' });
  expect(page.__cwErrors).toEqual([]);
});

test('native auth/REST: historical C02 → explicit built/reused → stored indicators and references', async ({ page }) => {
  await login(page);
  let builds = 0;
  page.on('request', request => { if (new URL(request.url()).pathname.endsWith('/rpc/build_evidence_bundle')) builds++; });
  await detail(page);
  await select(page).selectOption(fixture.customerA.older);
  await expect(evidence(page).getByText('Sem pacote para esta análise', { exact: true })).toBeVisible();
  await select(page).selectOption(fixture.customerA.primary);
  await expect(select(page).locator('option:checked')).toContainText('perfil v1');
  await expect(page.getByText('Promessa atual v2', { exact: true })).toBeVisible();
  expect(builds).toBe(0);
  const response = page.waitForResponse(rpc);
  await button(page).click();
  const result = await (await response).json();
  expect(result.status).toBe('built');
  await settled(page, await started(page, fixture.customerA.primary));
  const panel = evidence(page);
  await expect(panel.getByText(result.bundle_id, { exact: true })).toBeVisible();
  await expect(panel.getByText('Evidência íntegra', { exact: true })).toBeVisible();
  await expect(panel.getByText('Evidência insuficiente', { exact: true })).toBeVisible();
  await expect(panel.getByTestId('c03-snapshot-outcome')).toContainText('Baseline: 80');
  await expect(panel.getByTestId('c03-snapshot-notes')).toContainText('não registado');
  await expect(panel.getByTestId('c03-snapshot-notes')).not.toContainText('Baseline: 0');
  await panel.getByRole('button', { name: /^outcome/ }).click();
  await panel.getByRole('button', { name: 'Detalhe da referência 1', exact: true }).click();
  const reference = panel.getByTestId('c03-ref-detail-1');
  await expect(reference).toContainText('synthetic-ci');
  await expect(reference).toContainText('Recebido (UTC)');
  await expect(reference).toContainText('Corte do pacote (UTC)');
  await expect(reference.getByText(/^[0-9a-f]{64}$/)).toBeVisible();
  const hash = await panel.getByText(/^[0-9a-f]{64}$/).first().textContent();
  const reused = page.waitForResponse(rpc);
  await button(page).click();
  expect((await (await reused).json()).status).toBe('reused');
  await expect(page.getByText('Já existia um pacote para esta análise; foi reutilizado.', { exact: true })).toBeVisible();
  await select(page).selectOption(fixture.customerA.older);
  await expect(panel.getByText('Sem pacote para esta análise', { exact: true })).toBeVisible();
  await select(page).selectOption(fixture.customerA.primary);
  await expect(panel.getByText(result.bundle_id, { exact: true })).toBeVisible();
  await expect(panel.getByText(/^[0-9a-f]{64}$/).first()).toHaveText(hash);
  expect(builds).toBe(2);
  await page.screenshot({ path: 'logs/browser-historical-evidence.png', fullPage: true });
});

test('native RPC with controlled dispatch: A→B→A allows independent second build and ignores old feedback', async ({ page }) => {
  await login(page, 'operator');
  await detail(page);
  const held = holdBuilds(page); await held.install;
  await button(page).click();
  await expect.poll(() => held.calls.length).toBe(1);
  const original = await started(page, fixture.customerA.primary);
  await select(page).selectOption(fixture.customerA.older);
  await expect(select(page)).toHaveValue(fixture.customerA.older);
  await select(page).selectOption(fixture.customerA.primary);
  await expect(button(page)).toBeEnabled();
  await button(page).click();
  await expect.poll(() => held.calls.length).toBe(2);
  const current = await started(page, fixture.customerA.primary);
  expect(current).not.toBe(original);
  expect(held.calls).toEqual(Array(2).fill({ _tenant_id: fixture.tenantA, _run_id: fixture.customerA.primary }));
  held.gates[0].release(); await held.done[0].promise; await settled(page, original);
  await expect(button(page)).toBeDisabled();
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);
  expect(await page.evaluate(id => window.__CW_E2E_STATE__().events.some(e => e.id === id && e.status === 'success'), current)).toBe(false);
  held.gates[1].release(); await held.done[1].promise; await settled(page, current);
  await expect(button(page)).toBeEnabled();
  await expect(page.getByText('Já existia um pacote para esta análise; foi reutilizado.', { exact: true })).toBeVisible();
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(1);
  await page.screenshot({ path: 'logs/browser-independent-second-operation.png', fullPage: true });
});

for (const kind of ['customer', 'tenant', 'unmount']) {
  test(`native auth/data: ${kind} change clears old context while a build is in flight`, async ({ page }) => {
    await login(page); await detail(page);
    const held = holdBuilds(page); await held.install;
    await button(page).click(); await expect.poll(() => held.calls.length).toBe(1);
    const original = await started(page, fixture.customerA.primary);
    if (kind === 'tenant') {
      await page.getByRole('button', { name: /E2E Tenant A/ }).click();
      await page.getByRole('menuitem', { name: 'E2E Tenant B' }).click();
      await expect(page.getByRole('button', { name: /E2E Tenant B/ })).toBeVisible();
      await expect.poll(() => page.evaluate(tenant => window.__CW_E2E_STATE__().keys.some(k => k[0] === 't' && k[1] === tenant), fixture.tenantA)).toBe(false);
    } else {
      await page.getByRole('link', { name: 'Clientes', exact: true }).first().click();
      await expect(page.getByRole('heading', { name: 'Clientes', exact: true })).toBeVisible();
      if (kind === 'customer') {
        await page.getByRole('link').filter({ hasText: 'Outro Cliente A' }).click();
        await expect(page.getByRole('heading', { name: fixture.customerA2.name, exact: true })).toBeVisible();
        await expect(select(page)).toHaveValue(fixture.customerA2.primary);
      }
    }
    held.gates[0].release(); await held.done[0].promise; await settled(page, original);
    await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: fixture.customerA.name, exact: true })).toHaveCount(0);
    expect(held.calls).toEqual([{ _tenant_id: fixture.tenantA, _run_id: fixture.customerA.primary }]);
    if (kind === 'unmount') {
      await page.getByRole('link').filter({ hasText: fixture.customerA.name }).click();
      await expect(select(page)).toHaveValue(fixture.customerA.primary);
      await expect(button(page)).toBeEnabled();
    }
    if (kind === 'tenant') {
      await expect(page.getByText('Promessa atual v2', { exact: true })).toHaveCount(0);
      await expect(page.getByRole('button', { name: /Analisar agora|Montar pacote|Novo cliente/ })).toHaveCount(0);
    }
  });
}

for (const [status, code, message] of [
  ['rejected', 'ref_after_cutoff', /Montagem recusada: Uma observação foi importada depois da data de corte/],
  ['failed', 'internal_error:XX000', /Falha na montagem: Erro interno \(XX000\)/],
]) {
  test(`controlled C03 JSON ${status}; authentication and reads remain native`, async ({ page }) => {
    await login(page); await detail(page);
    await page.route(buildPath, route => route.fulfill({ json: { status, code } }));
    await button(page).click(); await settled(page, await started(page, fixture.customerA.primary));
    await expect(page.getByRole('alert').filter({ hasText: message })).toBeVisible();
    await expect(page.locator('[data-sonner-toast]')).toHaveCount(0);
  });
}

test('native viewer login can read evidence but has no analyze/build controls', async ({ page }) => {
  await login(page, 'viewer'); await detail(page);
  await expect(evidence(page).getByText('Evidência íntegra', { exact: true })).toBeVisible();
  await expect(button(page)).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Analisar agora/ })).toHaveCount(0);
});

test('mobile native login and historical evidence detail', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'operator'); await detail(page);
  await expect(evidence(page).getByTestId('c03-snapshot-outcome')).toContainText('Baseline: 80');
  await evidence(page).getByRole('button', { name: /^outcome/ }).click();
  await evidence(page).getByRole('button', { name: 'Detalhe da referência 1', exact: true }).click();
  await expect(evidence(page).getByTestId('c03-ref-detail-1')).toBeVisible();
  await page.screenshot({ path: 'logs/browser-mobile.png', fullPage: true });
});
