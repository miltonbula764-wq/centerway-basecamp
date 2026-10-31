import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { api, mockTransport } from "@/data/mock-adapter";
import { mapJourney, businessStatusOf } from "@/data/journey-mapper";
import { mockJourneys, clientId, DEMO_TENANT } from "@/data/mock/journeys";
import { L01Error, NO_AUTO_RETRY, canResendIdentically, preparePending, shouldAutoRetry } from "@/data/transport";
import { errorKindOf } from "@/components/cw/states";

const journeyOf = (n: number) => mockJourneys.find((j) => j.client_id === clientId(n))!;

describe("F06 journey → view models", () => {
  it("keeps parallel contracts and cases per client instead of one global state", () => {
    const vm = mapJourney(journeyOf(1), null);
    expect(vm.contracts).toHaveLength(2);
    const nexts = vm.workItems.map((w) => w.next);
    expect(nexts).toContain("supply_evidence_or_verification");
    expect(nexts).toContain("supply_context_or_open_investigation");
  });

  it("uses the latest contract revision and preserves the revision history", () => {
    const k = mapJourney(journeyOf(1), null).contracts.find((c) => c.revisions.length === 2)!;
    expect(k.revision).toBe(2);
    expect(k.revisions.map((r) => r.revision)).toEqual([1, 2]);
  });

  it("keeps facts, hypotheses, contradictions and missing information separate", () => {
    const inv = mapJourney(journeyOf(3), null).investigations.find((i) => i.report?.status === "inconclusivo")!;
    expect(inv.report!.facts.length).toBe(1);
    expect(inv.report!.hypotheses.length).toBe(1);
    expect(inv.report!.contradictions.length).toBe(1);
    expect(inv.report!.missing.length).toBe(2);
  });

  it("a client without contract only gets the append_value guidance", () => {
    expect(mapJourney(journeyOf(4), null).workItems.map((w) => w.next)).toEqual(["append_value"]);
  });

  it("without demo metadata the name falls back to the client id (no invented name)", () => {
    expect(mapJourney(journeyOf(2), null).displayName).toBe(`Cliente ${clientId(2).slice(0, 8)}`);
  });
});

describe("transport status vs business status", () => {
  it("a completed receipt can carry a blocked business result", () => {
    const r = mapJourney(journeyOf(6), null).receipts.find((x) => x.businessStatus === "blocked")!;
    expect(r.transportStatus).toBe("completed");
  });

  it("an error receipt exposes engine_rejected without reinterpretation", () => {
    const r = mapJourney(journeyOf(4), null).receipts[0]!;
    expect(r.transportStatus).toBe("error");
    expect(r.businessStatus).toBe("engine_rejected");
    expect(businessStatusOf(null)).toBeNull();
  });
});

describe("recovery without causality", () => {
  it("every journey declares causal attribution as not established", () => {
    for (const j of mockJourneys) expect(j.causal_attribution).toBe("not_established");
  });

  it("execution, observed improvement and contractual minimum stay separate", () => {
    const r = mapJourney(journeyOf(2), null).recoveries[0]!;
    expect(r.status).toBe("recuperacao_parcial");
    expect(r.executionSucceeded).toBe(true);
    expect(r.improvementObserved).toBe(true);
    expect(r.minimumMet).toBe(false);
  });

  it("a reversed intervention yields an inconclusive result with undetermined indicators", () => {
    const vm = mapJourney(journeyOf(3), null);
    expect(vm.decisions[0]!.reversed).toBe(true);
    expect(vm.recoveries[0]!.status).toBe("resultado_inconclusivo");
    expect(vm.recoveries[0]!.improvementObserved).toBeNull();
  });
});

describe("mock transport and errors", () => {
  it("operations are locked in L02.2", async () => {
    await expect(mockTransport.operate(DEMO_TENANT, clientId(1), { request_id: "x", operation: "detect", arguments: { contract_id: "c", revisions: [1], as_of: "2026-10-29T12:00:00Z", required_periods: 2 } })).rejects.toMatchObject({ status: 403 });
  });

  it("an invisible client returns 404", async () => {
    await expect(mockTransport.getJourney(DEMO_TENANT, "ffffffff-0000-4000-8000-000000000000")).rejects.toMatchObject({ status: 404 });
  });

  it("maps HTTP statuses and network loss to UI states", () => {
    expect(errorKindOf(new L01Error("http", 401, "session_expired"))).toBe("401");
    expect(errorKindOf(new L01Error("http", 409, "request_identity_conflict"))).toBe("409");
    expect(errorKindOf(new L01Error("http", 503, "unavailable"))).toBe("503");
    expect(errorKindOf(new L01Error("network", null, "network_unreachable"))).toBe("network");
  });

  it("the API client lists only clients authorised in the session", async () => {
    expect((await api.listCustomers()).length).toBe(6);
  });
});

describe("idempotent resend design", () => {
  it("never retries automatically, especially intervene and undo", () => {
    expect(NO_AUTO_RETRY).toEqual(expect.arrayContaining(["intervene", "undo"]));
    expect(shouldAutoRetry("intervene")).toBe(false);
    expect(shouldAutoRetry("undo")).toBe(false);
  });

  it("captures request_id before sending and only allows identical resend by the same principal", () => {
    const p = preparePending(DEMO_TENANT, clientId(1), "alice", { operation: "undo", arguments: { execution_id: "e" } }, () => "fixed-id");
    expect(p.request.request_id).toBe("fixed-id");
    expect(canResendIdentically(p, "alice")).toBe(true);
    expect(canResendIdentically(p, "reviewer")).toBe(false);
  });

  it("no source file stores anything in localStorage", () => {
    const walk = (d: string): string[] => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]));
    const offenders = walk("src").filter((f) => !f.includes("/test/") && /\.(ts|tsx)$/.test(f) && readFileSync(f, "utf8").includes("localStorage"));
    expect(offenders).toEqual([]);
  });
});

