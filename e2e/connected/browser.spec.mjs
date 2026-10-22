import { test, expect } from "@playwright/test";
import fs from "node:fs";
const fixture = JSON.parse(
  fs.readFileSync(new URL("../private/connected-browser.json", import.meta.url)),
);
async function login(page, user, tenant) {
  await page.route("**/*", (route) => {
    const u = new URL(route.request().url());
    return u.hostname === "127.0.0.1"
      ? route.continue()
      : u.hostname === "fonts.googleapis.com"
        ? route.fulfill({ contentType: "text/css", body: "" })
        : route.abort();
  });
  await page.addInitScript(
    (t) =>
      localStorage.getItem("centerway.selectedTenant") ||
      localStorage.setItem("centerway.selectedTenant", t),
    tenant,
  );
  await page.goto("/auth");
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Palavra-passe", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL(/\/app/);
  await page.goto("/app/conectar");
}
test("mobile: real login → controlled OAuth → discovery → human draft → approval blocked → disconnect", async ({
  page,
}) => {
  await login(page, fixture.user, fixture.tenant);
  await expect(page.getByText(/^Estado:/)).toBeVisible();
  if (await page.getByRole("button", { name: "Desligar e retirar consentimento" }).isVisible())
    await page.getByRole("button", { name: "Desligar e retirar consentimento" }).click();
  await expect(
    page.getByRole("button", { name: "Autorizar no PostHog", exact: true }),
  ).toBeVisible();
  const started = Date.now();
  await page.getByLabel("1. Que serviço SaaS oferece?").fill("Synthetic workflow SaaS");
  await page
    .getByLabel("3. Que resultado promete aos clientes?")
    .fill("Conclusão de fluxos documentados");
  await page.getByLabel(/5. Autorizo/).check();
  await page.getByRole("button", { name: "Autorizar no PostHog", exact: true }).click();
  await expect(page.getByText(/Escopo de um projeto confirmado/)).toBeVisible();
  expect(new URL(page.url()).search).toBe("");
  await page.getByRole("link", { name: "Voltar à ligação" }).click();
  await page.getByRole("button", { name: "company", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Confirme clientes e objetivos" })).toBeVisible();
  await page.getByLabel("Selecionar Acme synthetic", { exact: true }).check();
  await page.getByLabel("Nome de Acme synthetic", { exact: true }).fill("Cliente Acme confirmado");
  await page
    .getByLabel("Início do histórico a importar (UTC, até 366 dias)")
    .fill(new Date(Date.now() - 2 * 86400000).toISOString().slice(0, 10));
  await page.getByLabel("workflow_completed", { exact: true }).check();
  await page.getByLabel("Meta numérica, se documentada pelo responsável").fill("20");
  await page.getByLabel("Direção confirmada pelo responsável").selectOption("higher_is_better");
  await page.getByRole("button", { name: "Confirmar seleção e criar rascunho" }).click();
  await expect(
    page.getByRole("heading", { name: "Rever contrato antes da recolha" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Aprovar perfil e ativar sincronização" }).click();
  await expect(page.getByRole("alert")).toContainText("profile_contract_not_satisfied");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole("button", { name: "Desligar e retirar consentimento" }).click();
  await expect(page.getByText("Estado: Revogado", { exact: true })).toBeVisible();
  console.log(
    `Observed complete mobile cycle through disconnect: ${Date.now() - started}ms; controlled provider, no hosted OAuth.`,
  );
});
test("operator: connection controls unavailable; manual data path retained", async ({ page }) => {
  await login(page, fixture.operator, fixture.tenant);
  await expect(page.getByText(/A ligação requer um administrador/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Autorizar no PostHog" })).toHaveCount(0);
  await page.goto("/app/dados");
  await expect(page.getByRole("heading", { name: "Dados", exact: true })).toBeVisible();
});

test("A → B → A: delayed connected status cannot restore stale connection state", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page, fixture.user, fixture.tenant);
  await expect(page.getByText(/^Estado:/)).toBeVisible();
  let release, arrived;
  const hold = new Promise((r) => (release = r)),
    seen = new Promise((r) => (arrived = r));
  let intercepted = false;
  await page.route("**/api/connected/status?*", async (route) => {
    const u = new URL(route.request().url());
    if (!intercepted && u.searchParams.get("tenant") === fixture.tenant) {
      intercepted = true;
      arrived();
      await hold;
      await route
        .fulfill({
          contentType: "application/json",
          body: JSON.stringify({ status: "active", project_name: "STALE A CONNECTION" }),
        })
        .catch(() => {});
    } else await route.continue();
  });
  await page.reload();
  await seen;
  async function change(from, to) {
    await page.getByRole("button", { name: new RegExp(from) }).click();
    await page.getByRole("menuitem", { name: to, exact: true }).click();
    await expect(page).toHaveURL(/\/app$/);
    await page.goto("/app/conectar");
  }
  await change(fixture.tenantName, fixture.tenantBName);
  await expect(page.getByText(/^Estado:/)).toBeVisible();
  await change(fixture.tenantBName, fixture.tenantName);
  await expect(page.getByText(/^Estado:/)).toBeVisible();
  release();
  await expect(page.getByText("STALE A CONNECTION")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sincronizar um período agora" })).toHaveCount(0);
});
