// Browser-only synthetic API runtime. No mock imports, storage or credentials.
import { HttpTransport } from "./http-transport";
import { SessionController, type ControllerState } from "./session-controller";
import { computeKpis } from "./journey-mapper";
import { L01Error, type L01Transport } from "./transport";
import type { CustomerVM } from "@/domain/types";
import type { OperationRequest } from "@/domain/l01";
import type { CenterwayApiClient } from "./api-client";

export const API_ORIGIN = "https://centerway-synthetic-m67.onrender.com";
export interface LiveSnapshot {
  auth: Readonly<ControllerState>;
  customers: CustomerVM[];
  busy: boolean;
  error: unknown;
  revision: number;
}

export class LiveRuntime {
  readonly controller: SessionController;
  private generation = 0;
  private listeners = new Set<() => void>();
  private pending: Promise<void> | null = null;
  private snapshot: LiveSnapshot;
  constructor(transport: L01Transport, now?: () => number) {
    this.controller = new SessionController(transport, now);
    this.snapshot = { auth: this.controller.state, customers: [], busy: false, error: null, revision: 0 };
  }
  getSnapshot = () => this.snapshot;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  private publish(patch: Partial<LiveSnapshot> = {}) {
    this.snapshot = { ...this.snapshot, ...patch, auth: this.controller.state, revision: this.snapshot.revision + 1 };
    this.listeners.forEach((fn) => fn());
  }
  private current(generation: number) {
    if (generation !== this.generation) throw new L01Error("contract", null, "stale_response");
  }
  async login(username: string, password: string) {
    const g = ++this.generation;
    this.publish({ customers: [], busy: true, error: null });
    try {
      const login = this.controller.login(username, password);
      this.publish();
      await login; this.current(g);
      this.publish({ busy: false });
      const tenants = this.controller.state.clientTenants;
      if (tenants.length === 1) await this.selectTenant(tenants[0]!);
    } catch (error) {
      if (g === this.generation) this.publish({ busy: false, customers: [], error });
      throw error;
    }
  }
  async logout() {
    ++this.generation; this.pending = null;
    const revoke = this.controller.logout();
    this.publish({ customers: [], busy: false, error: null });
    try { await revoke; } catch { /* Local logout remains effective; server token expires. */ }
  }
  checkExpiry() {
    if (this.controller.state.status === "expired" && this.snapshot.auth.status !== "expired") {
      ++this.generation; this.pending = null;
      this.publish({ customers: [], busy: false, error: new L01Error("http", 401, "session_expired_locally") });
    }
  }
  async selectTenant(tenant: string) {
    const g = ++this.generation;
    this.publish({ customers: [], busy: true, error: null });
    const work = (async () => {
      try {
        const entries = await this.controller.selectTenant(tenant); this.current(g);
        const customers: CustomerVM[] = [];
        for (const entry of entries) {
          await this.controller.selectClient(entry.client_id); this.current(g);
          const view = this.controller.state.view;
          if (!view) throw new L01Error("contract", null, "journey_missing");
          customers.push(view);
        }
        this.current(g); this.publish({ customers, busy: false, error: null });
      } catch (error) {
        if (g === this.generation) this.publish({ customers: [], busy: false, error });
        throw error;
      } finally { if (g === this.generation) this.pending = null; }
    })();
    this.pending = work;
    return work;
  }
  async refresh() {
    const tenant = this.controller.state.tenant;
    if (tenant) await this.selectTenant(tenant);
  }
  async customers() {
    const g = this.generation;
    if (this.pending) await this.pending;
    this.current(g); this.checkExpiry();
    if (this.snapshot.error) throw this.snapshot.error;
    return this.snapshot.customers;
  }
  async prepare(client: string, request: OperationRequest) {
    if (!this.controller.canAttempt(request.operation)) throw new L01Error("http", 403, "operation_forbidden");
    const g = this.generation;
    await this.controller.selectClient(client); this.current(g);
    return this.controller.draft(request);
  }
  async submit(requestId: string) {
    const g = this.generation;
    try {
      const receipt = await this.controller.submit(requestId);
      this.current(g);
      return receipt;
    } catch (error) {
      if (g === this.generation && this.controller.state.status === "expired") {
        ++this.generation; this.publish({ customers: [], busy: false, error });
      }
      throw error;
    }
  }
}

let browserRuntime: LiveRuntime | undefined;
export function getLiveRuntime() {
  if (typeof window === "undefined") throw new Error("Browser-only session; SSR must be disabled for /app");
  return browserRuntime ??= new LiveRuntime(new HttpTransport({
    baseUrl: API_ORIGIN,
    fetch: (url, init) => {
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), 90_000);
      return window.fetch(url, { ...init, signal: abort.signal }).finally(() => clearTimeout(timer));
    },
  }));
}

const customers = () => getLiveRuntime().customers();
export const api: CenterwayApiClient = {
  mode: "live",
  listCustomers: customers,
  async getCustomer(id) { return (await customers()).find((c) => c.id === id) ?? null; },
  async getOverviewKpis() { return computeKpis(await customers()); },
  async listContracts() { return (await customers()).flatMap((c) => c.contracts); },
  async listInvestigations() { return (await customers()).flatMap((c) => c.investigations); },
  async listDecisions() { return (await customers()).flatMap((c) => c.decisions); },
  async listRecoveries() { return (await customers()).flatMap((c) => c.recoveries); },
  async listActivities() { return (await customers()).flatMap((c) => c.receipts.map((r) => ({ ...r, customerName: c.displayName }))).sort((a,b) => b.at.localeCompare(a.at)); },
};
export const customerName = (id: string) => getLiveRuntime().getSnapshot().customers.find((c) => c.id === id)?.displayName ?? `Cliente ${id.slice(0, 8)}`;
