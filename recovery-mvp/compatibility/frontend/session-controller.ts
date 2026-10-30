// HEADLESS session + navigation controller for the future L03 live phase.
// Not imported by the app. Works over any L01Transport (tests: FixtureTransport
// or HttpTransport with a simulated fetch). Never fires write operations on its
// own, never retries, never persists anything outside memory.
import type {
  ClientDirectoryEntry,
  OperationName,
  OperationRequest,
  OperationReceipt,
  SessionInfo,
  Uuid,
} from "@/domain/l01";
import type { ClientJourney } from "@/domain/f06";
import type { CustomerVM } from "@/domain/types";
import { mapJourney } from "./journey-mapper";
import { L01Error, listAllClients, type L01Transport } from "./transport";

export type SessionStatus =
  "logged_out" | "authenticating" | "authenticated" | "expired" | "forbidden" | "unavailable";

export type FlowStep =
  "company" | "client" | "journey" | "investigation" | "intervention" | "recovery";

/** What the journey actually shows — never assumes a step happened. */
export interface FlowProgress {
  contracts: number;
  detections: number;
  investigations: number;
  decisions: number;
  executedDecisions: number;
  recoveryPlans: number;
  evaluatedRecoveries: number;
  /** Furthest step with persisted evidence in the projection. */
  reached: FlowStep;
  causalAttribution: "not_established";
}

export interface OperationDraft {
  /** Scope binding: a draft is only valid for this exact principal/tenant/client. */
  principal: string;
  tenant: Uuid;
  client: Uuid;
  request: OperationRequest;
  lastError: { kind: L01Error["kind"]; status: number | null; code: string } | null;
}

export interface ControllerState {
  status: SessionStatus;
  session: SessionInfo | null;
  /** Company tenants (discover_company scope) — distinct from client-scope tenants. */
  companyTenants: Uuid[];
  /** Tenants that hold client scopes. Tenants have no display name in L01: ids only. */
  clientTenants: Uuid[];
  tenant: Uuid | null;
  directory: ClientDirectoryEntry[];
  client: Uuid | null;
  journey: ClientJourney | null;
  view: CustomerVM | null;
  lastError: { kind: L01Error["kind"]; status: number | null; code: string } | null;
}

/** Deep copy + deep freeze: stored drafts and returned copies can never be mutated. */
function frozenCopy<T>(v: T): T {
  const c = structuredClone(v);
  const freeze = (o: unknown) => {
    if (o && typeof o === "object" && !Object.isFrozen(o)) {
      Object.freeze(o);
      for (const k of Object.keys(o)) freeze((o as Record<string, unknown>)[k]);
    }
  };
  freeze(c);
  return c;
}

const empty = (): ControllerState => ({
  status: "logged_out",
  session: null,
  companyTenants: [],
  clientTenants: [],
  tenant: null,
  directory: [],
  client: null,
  journey: null,
  view: null,
  lastError: null,
});

export function deriveProgress(v: CustomerVM): FlowProgress {
  const detections = v.contracts.reduce((n, c) => n + c.detections.length, 0);
  const executedDecisions = v.decisions.filter((d) => d.status === "executed").length;
  const evaluatedRecoveries = v.recoveries.filter((r) => r.evaluated).length;
  const reached: FlowStep = v.recoveries.length
    ? "recovery"
    : v.decisions.length
      ? "intervention"
      : v.investigations.length
        ? "investigation"
        : "journey";
  return {
    contracts: v.contracts.length,
    detections,
    investigations: v.investigations.length,
    decisions: v.decisions.length,
    executedDecisions,
    recoveryPlans: v.recoveries.length,
    evaluatedRecoveries,
    reached,
    causalAttribution: v.causalAttribution,
  };
}

export class SessionController {
  private s: ControllerState = empty();
  private drafts = new Map<string, OperationDraft>();
  private expiresAt = 0;
  /** Bumped on every reset/tenant/client change; late async results from an older epoch are discarded. */
  private epoch = 0;

  constructor(
    private readonly t: L01Transport,
    private readonly now: () => number = () => Date.now(),
  ) {}

  get state(): Readonly<ControllerState> {
    if (this.s.status === "authenticated" && this.expiresAt && this.now() >= this.expiresAt) {
      this.reset("expired");
    }
    return this.s;
  }

  /** Server-provided operation scopes only; a UX hint, the server still decides. */
  canAttempt(op: OperationName): boolean {
    if (this.state.status !== "authenticated" || !this.s.session?.operations.includes(op))
      return false;
    // discover_company also needs a company tenant scope, distinct from client scopes.
    return op !== "discover_company" || this.s.companyTenants.length > 0;
  }

  private reset(status: SessionStatus, err: ControllerState["lastError"] = null) {
    this.s = { ...empty(), status, lastError: err };
    this.drafts.clear();
    this.expiresAt = 0;
    this.epoch++;
  }

  /** Map an error to session state. 401 wipes everything; 403 keeps the session. */
  private fail(e: unknown): never {
    const err =
      e instanceof L01Error
        ? { kind: e.kind, status: e.status, code: e.code }
        : { kind: "contract" as const, status: null, code: "unexpected_error" };
    if (err.status === 401) this.reset("expired", err);
    else if (err.status === 403) this.s = { ...this.s, status: "forbidden", lastError: err };
    else if (err.kind === "network" || err.status === 503)
      this.s = {
        ...this.s,
        status: this.s.session ? this.s.status : "unavailable",
        lastError: err,
      };
    else this.s = { ...this.s, lastError: err };
    throw e;
  }

  /**
   * reads: allowed when authenticated or forbidden (a 403 denies one resource, not the session).
   * writes (draft/submit): authenticated only. authenticating/unavailable: nothing, and no
   * silent re-authentication — the user must log in explicitly.
   */
  private guard(kind: "read" | "write" = "read") {
    const st = this.state.status;
    if (st === "expired" || st === "logged_out")
      throw new L01Error("http", 401, "session_expired_locally");
    if (st === "authenticating" || st === "unavailable" || !this.s.session)
      throw new L01Error("contract", null, "session_not_ready");
    if (kind === "write" && st === "forbidden")
      throw new L01Error("http", 403, "session_forbidden");
  }

  /** Throws if an async result belongs to a superseded epoch (switch, logout, 401). */
  private current(epoch: number) {
    if (epoch !== this.epoch) throw new L01Error("contract", null, "stale_response");
  }

  /** Error handling that never mutates state for a superseded request. */
  private failIfCurrent(epoch: number, e: unknown): never {
    this.current(epoch);
    this.fail(e);
  }

  /**
   * Last login wins. The epoch is captured after reset and re-checked after every
   * await and in the catch: a superseded login never authenticates, never resets
   * and never reports errors into a newer session. TTL counts from session
   * creation, not from the end of the getSession read.
   */
  async login(username: string, password: string): Promise<void> {
    this.reset("authenticating");
    const epoch = this.epoch;
    try {
      if (!this.t.createSession) throw new L01Error("contract", null, "login_unsupported");
      const created = await this.t.createSession({ username, password });
      this.current(epoch);
      const expiresAt = this.now() + created.expires_in * 1000;
      const session = await this.t.getSession();
      this.current(epoch);
      this.expiresAt = expiresAt;
      const clientTenants = Object.keys(session.clients).sort();
      this.s = {
        ...empty(),
        status: "authenticated",
        session,
        companyTenants: [...session.company_tenants],
        clientTenants,
      };
    } catch (e) {
      this.current(epoch);
      this.reset("logged_out");
      this.fail(e);
    }
  }

  /**
   * Local state is wiped immediately (before any await). The transport captures
   * the old credential synchronously for the revocation request, so a late
   * logout can never clear a newer login.
   */
  async logout(): Promise<void> {
    const revoke =
      (this.s.session || this.s.status === "authenticating") && this.t.deleteSession
        ? this.t.deleteSession()
        : null;
    this.reset("logged_out");
    if (revoke) await revoke;
  }

  /** Only tenants present in SessionInfo.clients can be selected. */
  async selectTenant(tenant: Uuid, pageSize?: number): Promise<ClientDirectoryEntry[]> {
    this.guard();
    if (!this.s.clientTenants.includes(tenant))
      throw new L01Error("http", 403, "tenant_not_in_session");
    this.s = {
      ...this.s,
      tenant,
      directory: [],
      client: null,
      journey: null,
      view: null,
      lastError: null,
    };
    const epoch = ++this.epoch;
    try {
      const directory = await listAllClients(this.t, tenant, pageSize);
      this.current(epoch);
      this.s = {
        ...this.s,
        status: this.s.status === "forbidden" ? "authenticated" : this.s.status,
        directory,
      };
      return directory;
    } catch (e) {
      this.failIfCurrent(epoch, e);
    }
  }

  /** Loads the journey; the server is the authority (403/404 surface as-is). */
  async selectClient(client: Uuid): Promise<FlowProgress> {
    this.guard();
    const tenant = this.s.tenant;
    if (!tenant) throw new L01Error("contract", null, "tenant_not_selected");
    // Local UX check only; the server remains the authority (403/404 still surface).
    if (!this.s.directory.some((d) => d.client_id === client))
      throw new L01Error("http", 403, "client_not_in_directory");
    this.s = { ...this.s, client, journey: null, view: null, lastError: null };
    const epoch = ++this.epoch;
    try {
      const journey = await this.t.getJourney(tenant, client);
      this.current(epoch);
      // Names: directory display_name only; no invented labels.
      const view = mapJourney(journey, null);
      const name = this.s.directory.find((d) => d.client_id === client)?.display_name;
      this.s = {
        ...this.s,
        // A successful server read clears a previous 403 on another resource.
        status: this.s.status === "forbidden" ? "authenticated" : this.s.status,
        journey,
        view: name ? { ...view, displayName: name } : view,
      };
      return deriveProgress(this.s.view!);
    } catch (e) {
      this.failIfCurrent(epoch, e);
    }
  }

  private key(principal: string, tenant: Uuid, client: Uuid, requestId: string) {
    return `${principal}|${tenant}|${client}|${requestId}`;
  }

  /** Memory-only draft bound to the current principal/tenant/client. Sends nothing. */
  draft(request: OperationRequest): OperationDraft {
    this.guard("write");
    const { session, tenant, client } = this.s;
    if (!session || !tenant || !client) throw new L01Error("contract", null, "scope_not_selected");
    const d: OperationDraft = {
      principal: session.principal,
      tenant,
      client,
      request: frozenCopy(request),
      lastError: null,
    };
    this.drafts.set(this.key(d.principal, tenant, client, d.request.request_id), d);
    return frozenCopy(d);
  }

  /** Frozen copies: callers cannot alter request_id/arguments of a stored draft. */
  listDrafts(): OperationDraft[] {
    return [...this.drafts.values()].map(frozenCopy);
  }

  /**
   * Explicit user action only. Exactly one attempt; on failure the identical
   * request (same request_id/arguments) is kept for an explicit resend.
   */
  async submit(requestId: string): Promise<OperationReceipt> {
    this.guard("write");
    const { session, tenant, client } = this.s;
    if (!session || !tenant || !client) throw new L01Error("contract", null, "scope_not_selected");
    const k = this.key(session.principal, tenant, client, requestId);
    const d = this.drafts.get(k);
    if (!d) throw new L01Error("contract", null, "draft_not_in_scope");
    const epoch = this.epoch;
    try {
      // Fresh frozen copy of the stored request: identical request_id/arguments on resend.
      const r = await this.t.operate(d.tenant, d.client, frozenCopy(d.request));
      // Receipt is returned even if the scope changed meanwhile (the server already acted);
      // only the draft bookkeeping is skipped for a superseded epoch.
      if (epoch === this.epoch) this.drafts.delete(k);
      return r;
    } catch (e) {
      if (epoch === this.epoch && e instanceof L01Error)
        d.lastError = { kind: e.kind, status: e.status, code: e.code };
      this.failIfCurrent(epoch, e);
    }
  }
}
