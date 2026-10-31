import type { CenterwayApiClient } from "./api-client";
import { L01Error, type L01Transport } from "./transport";
import { computeKpis, mapJourney } from "./journey-mapper";
import { demoClientMeta, mockJourneys, mockSession } from "./mock/journeys";
import type { CustomerVM } from "@/domain/types";

/** In-memory L01 transport: no network, no tokens, operations disabled. */
export const mockTransport: L01Transport = {
  mode: "demo",
  async getSession() {
    return mockSession;
  },
  async listClients(tenant, params) {
    // Demo directory over the demo session scopes; names are demo labels.
    const ids = [...(mockSession.clients[tenant] ?? [])].sort();
    const limit = params?.limit ?? 50;
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw new L01Error("http", 422, "invalid_parameters");
    const rest = params?.after ? ids.filter((id) => id > params.after!) : ids;
    const page = rest.slice(0, limit);
    return {
      data: page.map((id) => ({ client_id: id, display_name: demoClientMeta[id]?.company ?? `Cliente ${id.slice(0, 8)}` })),
      next_cursor: rest.length > limit ? page[page.length - 1]! : null,
      demo: true,
    };
  },
  async getJourney(tenant, client) {
    const j = mockJourneys.find((x) => x.tenant_id === tenant && x.client_id === client);
    if (!j) throw new L01Error("http", 404, "not_found");
    return j;
  },
  async operate() {
    // L02.2: every write stays locked until L03 (secure integration).
    throw new L01Error("http", 403, "disabled_until_secure_integration");
  },
};

/** Build the UI client over any transport (mock now; HTTP in L03). */
export function createApiClient(t: L01Transport, demoMeta: Record<string, CustomerVM["demo"]> = {}): CenterwayApiClient {
  async function customers(): Promise<CustomerVM[]> {
    const s = await t.getSession();
    const pairs = Object.entries(s.clients).flatMap(([tenant, ids]) => ids.map((c) => [tenant, c] as const));
    const journeys = await Promise.all(pairs.map(([tenant, c]) => t.getJourney(tenant, c)));
    return journeys.map((j) => mapJourney(j, demoMeta[j.client_id] ?? null));
  }
  return {
    mode: t.mode,
    async getOverviewKpis() {
      return computeKpis(await customers());
    },
    listCustomers: customers,
    async getCustomer(id) {
      return (await customers()).find((c) => c.id === id) ?? null;
    },
    async listContracts() {
      return (await customers()).flatMap((c) => c.contracts);
    },
    async listInvestigations() {
      return (await customers()).flatMap((c) => c.investigations);
    },
    async listDecisions() {
      return (await customers()).flatMap((c) => c.decisions);
    },
    async listRecoveries() {
      return (await customers()).flatMap((c) => c.recoveries);
    },
    async listActivities() {
      const cs = await customers();
      return cs
        .flatMap((c) => c.receipts.map((r) => ({ ...r, customerName: c.displayName })))
        .sort((a, b) => b.at.localeCompare(a.at));
    },
  };
}

export const api: CenterwayApiClient = createApiClient(mockTransport, demoClientMeta);

export const customerName = (id: string) => demoClientMeta[id]?.company ?? `Cliente ${id.slice(0, 8)}`;

