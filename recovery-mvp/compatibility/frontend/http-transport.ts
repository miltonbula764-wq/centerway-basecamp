// INACTIVE HTTP implementation of L01Transport (contract c02-v1) for the future
// L03 live phase. Nothing in the app imports this module: the runtime uses
// mockTransport only. It never reads env vars, never touches storage, never
// logs, and never retries. Tests drive it with an injected fetch.
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

export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export interface HttpTransportConfig {
  /** Explicit HTTPS origin, e.g. "https://api.example". Required; no default. */
  baseUrl: string;
  /** Injected fetch. Required so nothing can fall back to the global network. */
  fetch: FetchLike;
  /** Allow https://localhost / 127.0.0.1 (local TLS tests only). Default false. */
  allowLocalhost?: boolean;
  /** Clock for token expiry (ms). */
  now?: () => number;
}

export class HttpTransportConfigError extends Error {
  constructor(code: string) {
    super(code);
    this.name = "HttpTransportConfigError";
  }
}

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0"]);
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Validate and normalise the base URL. HTTPS only, origin only, no credentials. */
export function parseBaseUrl(raw: unknown, allowLocalhost = false): string {
  if (typeof raw !== "string" || raw.trim() === "")
    throw new HttpTransportConfigError("base_url_missing");
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    throw new HttpTransportConfigError("base_url_invalid");
  }
  if (u.protocol !== "https:") throw new HttpTransportConfigError("base_url_not_https");
  if (u.username || u.password) throw new HttpTransportConfigError("base_url_has_credentials");
  if (u.search || u.hash || raw.includes("?") || raw.includes("#"))
    throw new HttpTransportConfigError("base_url_has_query");
  if (u.pathname !== "/" && u.pathname !== "")
    throw new HttpTransportConfigError("base_url_has_path");
  if (!allowLocalhost && (LOCAL_HOSTS.has(u.hostname) || u.hostname.endsWith(".localhost")))
    throw new HttpTransportConfigError("base_url_localhost");
  return u.origin;
}

function assertUuid(v: string, what: string) {
  if (!UUID_RE.test(v)) throw new L01Error("contract", null, `invalid_${what}`);
}

export class HttpTransport implements L01Transport {
  readonly mode = "live" as const;
  private readonly base: string;
  private readonly fetchFn: FetchLike;
  private readonly now: () => number;
  /** Memory only. Never persisted, never logged, never exposed. */
  #token: string | null = null;
  #expiresAt = 0;
  /** Credential generation: bumped on every login/logout/clear. Late responses from an older generation never install, clear or replace the current token. */
  #gen = 0;

  constructor(cfg: HttpTransportConfig) {
    if (!cfg || typeof cfg.fetch !== "function")
      throw new HttpTransportConfigError("fetch_missing");
    this.base = parseBaseUrl(cfg.baseUrl, cfg.allowLocalhost ?? false);
    this.fetchFn = cfg.fetch;
    this.now = cfg.now ?? (() => Date.now());
  }

  get hasSession(): boolean {
    return this.#token !== null && this.now() < this.#expiresAt;
  }

  private clear() {
    this.#token = null;
    this.#expiresAt = 0;
    this.#gen++;
  }

  private async send(
    method: "GET" | "POST" | "DELETE",
    path: string,
    opts: { json?: unknown; auth?: boolean; token?: string } = {},
  ): Promise<{ status: number; body: unknown }> {
    const headers: Record<string, string> = { Accept: "application/json" };
    const gen = this.#gen;
    if (opts.token !== undefined) {
      headers["Authorization"] = `Bearer ${opts.token}`;
    } else if (opts.auth !== false) {
      if (!this.#token || this.now() >= this.#expiresAt) {
        this.clear();
        throw new L01Error("http", 401, "session_expired_locally");
      }
      headers["Authorization"] = `Bearer ${this.#token}`;
    }
    const init: RequestInit = {
      method,
      headers,
      // Never follow redirects: a redirect could forward the bearer to another origin.
      redirect: "error",
      credentials: "omit",
      cache: "no-store",
      referrerPolicy: "no-referrer",
    };
    if (opts.json !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.json);
    }
    let res: Response;
    try {
      res = await this.fetchFn(this.base + path, init);
    } catch {
      throw new L01Error("network", null, "network_unreachable");
    }
    if (res.type === "opaqueredirect" || (res.status >= 300 && res.status < 400))
      throw new L01Error("contract", res.status, "unexpected_redirect");
    let json: unknown = null;
    if (res.status !== 204) {
      const text = await res.text().catch(() => "");
      if (text) {
        try {
          json = JSON.parse(text);
        } catch {
          json = null;
        }
      }
    }
    try {
      return { status: res.status, body: classifyResponse(res.status, json) };
    } catch (e) {
      // Only a 401 for the current credential generation clears it.
      if (
        e instanceof L01Error &&
        e.status === 401 &&
        opts.auth !== false &&
        opts.token === undefined &&
        gen === this.#gen
      )
        this.clear();
      throw e;
    }
  }

  async createSession(login: LoginRequest): Promise<SessionCreated> {
    this.clear();
    const gen = this.#gen;
    let res: { status: number; body: unknown };
    try {
      res = await this.send("POST", "/v1/sessions", { json: login, auth: false });
    } catch (e) {
      if (gen !== this.#gen) throw new L01Error("contract", null, "stale_response");
      throw e;
    }
    if (gen !== this.#gen) throw new L01Error("contract", null, "stale_response");
    const { status, body } = res;
    const b = body as Partial<SessionCreated>;
    if (
      status !== 201 ||
      b.token_type !== "Bearer" ||
      typeof b.access_token !== "string" ||
      b.access_token === "" ||
      typeof b.expires_in !== "number" ||
      !(b.expires_in > 0)
    ) {
      throw new L01Error("contract", status, "unexpected_session_created");
    }
    this.#token = b.access_token;
    this.#expiresAt = this.now() + b.expires_in * 1000;
    // The caller never receives the token itself.
    return { ...(b as SessionCreated), access_token: "[memory-only]" };
  }

  async getSession(): Promise<SessionInfo> {
    const { status, body } = await this.send("GET", "/v1/session");
    const b = body as Partial<SessionInfo>;
    if (
      typeof b.username !== "string" ||
      typeof b.principal !== "string" ||
      !b.clients ||
      typeof b.clients !== "object" ||
      !Array.isArray(b.operations) ||
      !Array.isArray(b.company_tenants)
    ) {
      throw new L01Error("contract", status, "unexpected_session");
    }
    return b as SessionInfo;
  }

  async deleteSession(): Promise<void> {
    // Capture the old credential, clear immediately, then revoke with the captured token.
    const token = this.#token && this.now() < this.#expiresAt ? this.#token : null;
    this.clear();
    if (!token) return;
    const { status, body } = await this.send("DELETE", "/v1/session", { token });
    if (status !== 204 || body !== undefined)
      throw new L01Error("contract", status, "unexpected_logout");
  }

  async listClients(tenant: Uuid, params?: ListClientsParams): Promise<ClientDirectoryPage> {
    assertUuid(tenant, "tenant");
    const q = new URLSearchParams();
    if (params?.limit !== undefined) {
      if (!Number.isInteger(params.limit) || params.limit < 1 || params.limit > 100)
        throw new L01Error("contract", null, "invalid_limit");
      q.set("limit", String(params.limit));
    }
    if (params?.after !== undefined) {
      assertUuid(params.after, "cursor");
      q.set("after", params.after);
    }
    const qs = q.toString();
    const { status, body } = await this.send(
      "GET",
      `/v1/tenants/${tenant}/clients${qs ? `?${qs}` : ""}`,
    );
    return directoryPageOf(body, status);
  }

  async getJourney(tenant: Uuid, client: Uuid): Promise<ClientJourney> {
    assertUuid(tenant, "tenant");
    assertUuid(client, "client");
    const { body } = await this.send("GET", `/v1/tenants/${tenant}/clients/${client}/journey`);
    return validateJourneyEnvelope(body, { tenant, client });
  }

  /** Single attempt only. A lost response is resent explicitly by the user with the same request. */
  async operate(tenant: Uuid, client: Uuid, req: OperationRequest): Promise<OperationReceipt> {
    assertUuid(tenant, "tenant");
    assertUuid(client, "client");
    if (!req || typeof req.request_id !== "string" || !UUID_RE.test(req.request_id))
      throw new L01Error("contract", null, "request_id_required");
    const { status, body } = await this.send(
      "POST",
      `/v1/tenants/${tenant}/clients/${client}/operations`,
      {
        json: { request_id: req.request_id, operation: req.operation, arguments: req.arguments },
      },
    );
    return receiptOf(body, status);
  }
}
