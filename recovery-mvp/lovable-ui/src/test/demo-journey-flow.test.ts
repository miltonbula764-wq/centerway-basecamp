// L03.3: offline audit of the journey a user can navigate TODAY in demo mode,
// over the runtime `api` (mock adapter). No fixtures bundled, no network.
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { api } from "@/data/mock-adapter";

describe("demo journey: Empresa → Cliente → Valor → Deterioração → Investigação → Intervenção → Recuperação", () => {
  it("client selection: every listed client resolves to a detail; unknown id is null", async () => {
    const list = await api.listCustomers();
    expect(list.length).toBeGreaterThan(0);
    for (const c of list) {
      expect((await api.getCustomer(c.id))?.id).toBe(c.id);
      expect(c.demo).not.toBeNull(); // name/plan/etc. are labelled demo-only
    }
    expect(await api.getCustomer("does-not-exist")).toBeNull();
  });

  it("chain links stay inside one client (no cross-client leakage)", async () => {
    for (const c of await api.listCustomers()) {
      const contracts = new Set(c.contracts.map((k) => k.id));
      const dets = new Set(c.contracts.flatMap((k) => k.detections.map((d) => d.id)));
      const invs = new Set(c.investigations.map((i) => i.id));
      const decs = new Set(c.decisions.map((d) => d.id));
      for (const k of c.contracts) expect(k.customerId).toBe(c.id);
      for (const i of c.investigations) {
        expect(i.customerId).toBe(c.id);
        expect(contracts.has(i.contractId)).toBe(true);
        expect(dets.has(i.detectionId)).toBe(true);
      }
      for (const d of c.decisions) {
        expect(d.customerId).toBe(c.id);
        expect(invs.has(d.investigationId)).toBe(true);
      }
      for (const r of c.recoveries) {
        expect(r.customerId).toBe(c.id);
        expect(decs.has(r.decisionId)).toBe(true);
        expect(contracts.has(r.contractId)).toBe(true);
      }
    }
  });

  it("every step is represented somewhere in the demo data", async () => {
    const all = await api.listCustomers();
    expect(all.some((c) => c.contracts.length)).toBe(true);
    expect(all.some((c) => c.contracts.some((k) => k.detections.length))).toBe(true);
    expect(all.some((c) => c.investigations.some((i) => i.report))).toBe(true);
    expect(all.some((c) => c.decisions.length)).toBe(true);
    const recs = all.flatMap((c) => c.recoveries);
    expect(recs.some((r) => r.evaluated)).toBe(true);
    expect(new Set(recs.map((r) => r.status)).size).toBeGreaterThan(1);
  });

  it("recovery never claims causality nor equates execution with recovery", async () => {
    for (const c of await api.listCustomers()) {
      expect(c.causalAttribution).toBe("not_established");
      for (const r of c.recoveries) {
        // Planned but not evaluated: no outcome may be shown.
        if (!r.evaluated) expect(r.status).toBeNull();
        // Complete recovery requires the contractual minimum, not just a successful execution.
        if (r.status === "recuperacao_completa") expect(r.minimumMet).toBe(true);
        if (r.minimumMet === false) expect(r.status).not.toBe("recuperacao_completa");
      }
    }
    const statuses = new Set((await api.listRecoveries()).map((r) => r.status));
    expect(statuses.has("recuperacao_completa")).toBe(true);
    expect(statuses.has("resultado_inconclusivo")).toBe(true);
  });

  it("aggregated lists equal the union of per-client data (pages stay consistent)", async () => {
    const all = await api.listCustomers();
    const ids = (xs: { id: string }[]) => xs.map((x) => x.id).sort();
    expect(ids(await api.listContracts())).toEqual(ids(all.flatMap((c) => c.contracts)));
    expect(ids(await api.listInvestigations())).toEqual(ids(all.flatMap((c) => c.investigations)));
    expect(ids(await api.listDecisions())).toEqual(ids(all.flatMap((c) => c.decisions)));
    expect(ids(await api.listRecoveries())).toEqual(ids(all.flatMap((c) => c.recoveries)));
  });

  it("live application never imports mocks or capture fixtures", () => {
    const walk = (d: string): string[] =>
      readdirSync(d).flatMap((f) => {
        const p = join(d, f);
        if (p.includes("/test")) return [];
        return statSync(p).isDirectory() ? walk(p) : /\.tsx?$/.test(p) ? [p] : [];
      });
    for (const f of walk(join(__dirname, ".."))) {
      if (/http-transport|session-controller|fixture-transport|mock-adapter|mock-journeys/.test(f)) continue;
      expect(readFileSync(f, "utf8")).not.toMatch(
        /mock-adapter|mock-journeys|fixture-transport|fixtures\//,
      );
    }
  });
});

