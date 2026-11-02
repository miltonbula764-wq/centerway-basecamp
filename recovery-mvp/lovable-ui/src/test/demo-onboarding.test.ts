import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { describe, expect, it } from "vitest";
import { routeTree } from "@/routeTree.gen";
import { demoCompanyLabel, demoConcepts, demoProvenance } from "@/components/cw/demo-guide";
import { api } from "@/data/mock-adapter";

const router = () => createRouter({ routeTree, context: { queryClient: new QueryClient() } });

describe("L04 demo onboarding", () => {
  it("labels everything as synthetic demo data", () => {
    expect(demoProvenance).toBe("DEMONSTRAÇÃO — dados sintéticos");
    expect(demoCompanyLabel).toBe("Empresa de demonstração");
  });

  it("explains exactly the three concepts and never claims causality", () => {
    expect(demoConcepts.map((c) => c.term)).toEqual([
      "Valor prometido",
      "Deterioração",
      "Recuperação observada",
    ]);
    const recovery = demoConcepts[2].text;
    expect(recovery).toMatch(/não prova/);
    for (const c of demoConcepts) expect(c.text).not.toMatch(/\d|recupera automaticamente|garant/i);
  });

  it("entry CTAs resolve to real routes backed by mock data", async () => {
    const r = router();
    expect(r.matchRoutes("/app/clientes").at(-1)?.routeId).toBe("/app/clientes/");
    const customers = await api.listCustomers();
    expect(customers.length).toBeGreaterThan(0);
    const first = customers[0]!;
    expect(r.matchRoutes(`/app/clientes/${first.id}`).at(-1)?.routeId).toBe("/app/clientes/$id");
    expect(await api.getCustomer(first.id)).not.toBeNull();
  });
});

