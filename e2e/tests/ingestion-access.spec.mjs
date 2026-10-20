import { test, expect } from "@playwright/test";
import fs from "node:fs";
const f = JSON.parse(fs.readFileSync(new URL("../team-fixtures.json", import.meta.url)));
const users = JSON.parse(fs.readFileSync(new URL("../private/team-users.json", import.meta.url)));
// One-time secrets must never appear in browser artifacts.
test.use({ screenshot: "off", trace: "off", video: "off" });
async function login(page, user = users.admin, tenant = f.tenant) {
  await page.route("**/*", (route) => {
    const u = new URL(route.request().url());
    if (["127.0.0.1", "localhost"].includes(u.hostname)) return route.continue();
    if (u.hostname === "fonts.googleapis.com")
      return route.fulfill({ contentType: "text/css", body: "" });
    return route.abort();
  });
  await page.addInitScript((t) => {
    if (!localStorage.getItem("centerway.selectedTenant"))
      localStorage.setItem("centerway.selectedTenant", t);
  }, f.tenant);
  await page.goto("/auth");
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Palavra-passe", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:$|[/?])/);
  await page.goto("/app/configuracoes");
}
async function fill(page, name = "[SYNTHETIC] Browser ingestion") {
  const form = page.getByRole("form", { name: "Criar credencial de ingestão" });
  await form.getByLabel("Nome da integração", { exact: true }).fill(name);
  await form.getByLabel("Fonte exata autorizada", { exact: true }).fill("synthetic-browser");
  await form
    .getByLabel("Validade (hora local, até 365 dias)", { exact: true })
    .fill(new Date(Date.now() + 3600000).toISOString().slice(0, 16));
  return form;
}
test("real authenticated admin creates, copies, reloads metadata, rotates and revokes a C01-only key", async ({
  page,
}) => {
  await login(page);
  const form = await fill(page);
  await form.getByRole("button", { name: "Criar credencial", exact: true }).click();
  await expect(page.getByLabel("Segredo apresentado uma única vez", { exact: true })).toBeVisible();
  const secret = await page
    .getByLabel("Segredo apresentado uma única vez", { exact: true })
    .inputValue();
  expect(secret.startsWith("cw_ingest_v1_")).toBe(true);
  const id = secret.slice(13).split(".")[0];
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "Copiar credencial", exact: true }).click();
  expect((await page.evaluate(() => navigator.clipboard.readText())) === secret).toBe(true);
  await page.reload();
  await expect(page.getByLabel("Segredo apresentado uma única vez", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByText(`ID: ${id}`, { exact: true })).toBeVisible();
  const rotate = await fill(page, "[SYNTHETIC] Browser rotated");
  await rotate.getByLabel("Rotação opcional · ID da credencial atual", { exact: true }).fill(id);
  await rotate.getByRole("button", { name: "Criar credencial", exact: true }).click();
  await expect(page.getByLabel("Segredo apresentado uma única vez", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Revogar [SYNTHETIC] Browser rotated", exact: true })
    .click();
  await expect(page.getByLabel("Segredo apresentado uma única vez", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "Revogar [SYNTHETIC] Browser rotated", exact: true }),
  ).toHaveCount(0);
});
test("late credential response cannot expose an A secret in B; reload, viewer and logout keep caches isolated", async ({
  page,
}) => {
  await login(page);
  const form = await fill(page, "[SYNTHETIC] Late response");
  let release, started;
  const gate = new Promise((r) => {
    release = r;
  });
  const dispatched = new Promise((r) => {
    started = r;
  });
  await page.route("**/rest/v1/rpc/create_ingestion_credential", async (route) => {
    const response = await route.fetch();
    started();
    await gate;
    await route.fulfill({ response }).catch(() => {});
  });
  await form.getByRole("button", { name: "Criar credencial", exact: true }).click();
  await dispatched;
  await page.getByRole("button", { name: /Equipa SaaS A/ }).click();
  await page.getByRole("menuitem", { name: /Equipa SaaS B/ }).click();
  release();
  await page.getByRole("link", { name: "Configurações", exact: true }).click();
  await expect(
    page.getByText("A gestão de credenciais exige um administrador.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Segredo apresentado uma única vez", { exact: true })).toHaveCount(
    0,
  );
  await expect(page.getByRole("form", { name: "Criar credencial de ingestão" })).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(() =>
        window
          .__CW_E2E_STATE__()
          .keys.filter((k) => k[0] === "t")
          .every((k) => k[1] === localStorage.getItem("centerway.selectedTenant")),
      ),
    )
    .toBe(true);
  await page.reload();
  await expect(
    page.getByText("A gestão de credenciais exige um administrador.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Terminar sessão", exact: true }).first().click();
  await expect(page).toHaveURL(/\/auth/);
  await expect
    .poll(() =>
      page.evaluate(() => window.__CW_E2E_STATE__().keys.filter((k) => k[0] === "t").length),
    )
    .toBe(0);
});

test("persisted API failures and last use are visible to the real tenant admin without re-exposing any secret", async ({
  page,
}) => {
  const api = JSON.parse(fs.readFileSync(new URL("../api-fixtures.json", import.meta.url)));
  const accounts = JSON.parse(
    fs.readFileSync(new URL("../private/mvp-users.json", import.meta.url)),
  );
  await login(page, accounts.admin, api.tenant);
  await expect(
    page.getByRole("heading", { name: "Histórico HTTP (sem segredos)", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/unknown_subject/).first()).toBeVisible();
  await expect(page.getByText(/Última utilização:/).first()).toBeVisible();
  await expect(page.getByLabel("Segredo apresentado uma única vez", { exact: true })).toHaveCount(
    0,
  );
});
