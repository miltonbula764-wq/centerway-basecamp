// Offline, deterministic L01Transport over the Codex L03-PREP capture bundle
// (fixture_version l03-prep-v1). Test-only: the bundle is injected by the
// caller and is never imported by the app. No fetch, no tokens, no retries.
//
// The 71 captures are ordered events from one stateful run, so the transport
// does NOT answer by lookup: each call must be armed with a case id and must
// match that case's method, path and JSON body exactly. Anything else fails
// explicitly — there is no fallback to mock data.
import type { ClientJourney } from "@/domain/f06";
import type {
  ClientDirectoryPage,
  ListClientsParams,
  LoginRequest,
  OperationReceipt,
  OperationRequest,
  SessionCreated,
  SessionInfo,
  Uuid,
} from "@/domain/l01";
import { validateJourneyEnvelope } from "./journey-mapper";
import {
  L01Error,
  classifyResponse,
  directoryPageOf,
  receiptOf,
  type L01Transport,
} from "./transport";

export type FixtureActor = "alice" | "reviewer" | "reader" | "bob";

export interface FixtureCase {
  id: string;
  actor: FixtureActor;
  request: {
    method: "GET" | "POST" | "DELETE";
    path: string;
    json: Record<string, unknown> | null;
  };
  response: { status: number; json: Record<string, unknown> | null } | null;
  transport_error: null | "connection_refused";
}

export interface FixtureBundle {
  fixture_version: "l03-prep-v1";
  synthetic_only: true;
  source: "real-local-c03-https-api";
  base_commit: string;
  contracts: Record<string, string>;
  sanitization: "typed-placeholders-v1";
  cases: FixtureCase[];
}

export class FixtureMismatchError extends Error {
  constructor(
    readonly caseId: string | null,
    detail: string,
  ) {
    super(`fixture ${caseId ?? "<none armed>"}: ${detail}`);
    this.name = "FixtureMismatchError";
  }
}

/** Stable JSON for exact comparison (key order independent). */
function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(",")}]`;
  if (v && typeof v === "object") {
    return `{${Object.keys(v as object)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${canonical((v as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(v ?? null);
}

function query(params?: ListClientsParams): string {
  const q: string[] = [];
  if (params?.limit !== undefined) q.push(`limit=${params.limit}`);
  if (params?.after !== undefined) q.push(`after=${params.after}`);
  return q.length ? `?${q.join("&")}` : "";
}

export function validateBundle(b: unknown): FixtureBundle {
  const x = b as FixtureBundle;
  if (
    !x ||
    x.fixture_version !== "l03-prep-v1" ||
    x.synthetic_only !== true ||
    x.source !== "real-local-c03-https-api" ||
    x.sanitization !== "typed-placeholders-v1"
  ) {
    throw new Error("fixture bundle header mismatch");
  }
  if (!Array.isArray(x.cases) || new Set(x.cases.map((c) => c.id)).size !== x.cases.length)
    throw new Error("fixture case ids missing or duplicated");
  return x;
}

export class FixtureTransport implements L01Transport {
  readonly mode = "demo" as const;
  private readonly byId: Map<string, FixtureCase>;
  private armed: FixtureCase | null = null;
  /** Ids actually replayed, in order. */
  readonly replayed: string[] = [];

  constructor(bundle: FixtureBundle) {
    this.byId = new Map(validateBundle(bundle).cases.map((c) => [c.id, c]));
  }

  /** Arm exactly one case for the next call. */
  expect(caseId: string, actor?: FixtureActor): this {
    const c = this.byId.get(caseId);
    if (!c) throw new FixtureMismatchError(caseId, "unknown case id");
    if (actor && c.actor !== actor)
      throw new FixtureMismatchError(caseId, `actor ${actor} ≠ ${c.actor}`);
    this.armed = c;
    return this;
  }

  /** Low-level replay: verify the request, then return the classified body. */
  async request(
    method: FixtureCase["request"]["method"],
    path: string,
    json: unknown = null,
  ): Promise<{ status: number; body: unknown }> {
    const c = this.armed;
    this.armed = null;
    if (!c) throw new FixtureMismatchError(null, `${method} ${path} without an armed case`);
    if (c.request.method !== method || c.request.path !== path) {
      throw new FixtureMismatchError(
        c.id,
        `request ${method} ${path} ≠ ${c.request.method} ${c.request.path}`,
      );
    }
    if (canonical(c.request.json) !== canonical(json))
      throw new FixtureMismatchError(c.id, "request body differs from capture");
    this.replayed.push(c.id);
    if (c.response === null) {
      // No HTTP response was captured: a transport failure, not an HTTP 503.
      throw new L01Error("network", null, c.transport_error ?? "network_unreachable");
    }
    return {
      status: c.response.status,
      body: classifyResponse(c.response.status, c.response.json),
    };
  }

  async createSession(login: LoginRequest): Promise<SessionCreated> {
    const { status, body } = await this.request("POST", "/v1/sessions", login);
    const b = body as Partial<SessionCreated>;
    if (
      status !== 201 ||
      b.token_type !== "Bearer" ||
      typeof b.access_token !== "string" ||
      typeof b.expires_in !== "number"
    ) {
      throw new L01Error("contract", status, "unexpected_session_created");
    }
    return b as SessionCreated;
  }

  async getSession(): Promise<SessionInfo> {
    const { status, body } = await this.request("GET", "/v1/session");
    const b = body as Partial<SessionInfo>;
    if (
      typeof b.username !== "string" ||
      typeof b.principal !== "string" ||
      !b.clients ||
      !Array.isArray(b.operations) ||
      !Array.isArray(b.company_tenants)
    ) {
      throw new L01Error("contract", status, "unexpected_session");
    }
    return b as SessionInfo;
  }

  async deleteSession(): Promise<void> {
    const { status, body } = await this.request("DELETE", "/v1/session");
    if (status !== 204 || body !== undefined)
      throw new L01Error("contract", status, "unexpected_logout");
  }

  async listClients(tenant: Uuid, params?: ListClientsParams): Promise<ClientDirectoryPage> {
    const { status, body } = await this.request(
      "GET",
      `/v1/tenants/${tenant}/clients${query(params)}`,
    );
    return directoryPageOf(body, status);
  }

  async getJourney(tenant: Uuid, client: Uuid): Promise<ClientJourney> {
    const { body } = await this.request("GET", `/v1/tenants/${tenant}/clients/${client}/journey`);
    return validateJourneyEnvelope(body, { tenant, client });
  }

  async operate(tenant: Uuid, client: Uuid, req: OperationRequest): Promise<OperationReceipt> {
    const { status, body } = await this.request(
      "POST",
      `/v1/tenants/${tenant}/clients/${client}/operations`,
      req,
    );
    return receiptOf(body, status);
  }
}

