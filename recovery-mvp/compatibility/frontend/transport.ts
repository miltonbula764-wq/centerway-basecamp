// Transport port mirroring L01 (openapi c02-v1). The app ships only the mock
// implementation; FixtureTransport (offline, tests) and the future HTTP
// transport implement this same interface.
import type { ClientJourney } from "@/domain/f06";
import type {
  ClientDirectoryPage,
  ListClientsParams,
  LoginRequest,
  OperationName,
  OperationReceipt,
  OperationRequest,
  SessionCreated,
  SessionInfo,
  Uuid,
} from "@/domain/l01";

/**
 * http     — rejected by the HTTP layer before any engine ran (ErrorEnvelope, no receipt).
 * receipt  — the engine rejected the command and an error receipt was persisted.
 * network  — no HTTP response at all (refused, TLS, CORS…). Never an invented 503.
 * contract — a response arrived but does not match the documented shape/version.
 */
export type TransportErrorKind = "http" | "receipt" | "network" | "contract";

/** Error surfaced exactly as received — never masked or reinterpreted. */
export class L01Error extends Error {
  constructor(
    readonly kind: TransportErrorKind,
    readonly status: number | null,
    readonly code: string,
    /** Present when the engine stored an error receipt. Its sqlstate is not UI copy. */
    readonly receipt?: OperationReceipt,
  ) {
    super(kind === "network" ? "network_unreachable" : `${status ?? "-"} ${code}`);
    this.name = "L01Error";
  }
}

export interface L01Transport {
  readonly mode: "demo" | "live";
  createSession?(login: LoginRequest): Promise<SessionCreated>;
  getSession(): Promise<SessionInfo>;
  /** DELETE /v1/session → 204, no body. */
  deleteSession?(): Promise<void>;
  listClients(tenant: Uuid, params?: ListClientsParams): Promise<ClientDirectoryPage>;
  getJourney(tenant: Uuid, client: Uuid): Promise<ClientJourney>;
  operate(tenant: Uuid, client: Uuid, request: OperationRequest): Promise<OperationReceipt>;
}

const isObj = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);

const isReceipt = (v: unknown): v is OperationReceipt =>
  isObj(v) &&
  typeof v["request_id"] === "string" &&
  typeof v["operation"] === "string" &&
  (v["status"] === "completed" || v["status"] === "error");

/**
 * Classify one HTTP outcome into a body or an L01Error. Pure: shared by the
 * offline FixtureTransport and the future HTTP transport.
 * - 204 → undefined (no JSON parse).
 * - 2xx → body as received (HTTP 200 is NOT business success).
 * - error receipt (data.status="error") → kind "receipt", code engine_rejected.
 * - ErrorEnvelope → kind "http" with the server code.
 */
export function classifyResponse(status: number, json: unknown): unknown {
  if (status === 204) return undefined;
  if (status >= 200 && status < 300) {
    if (!isObj(json)) throw new L01Error("contract", status, "unexpected_body");
    return json;
  }
  if (isObj(json) && isReceipt(json["data"]) && json["data"].status === "error") {
    const result = json["data"].result;
    const code =
      isObj(result) && typeof result["code"] === "string" ? result["code"] : "engine_rejected";
    throw new L01Error("receipt", status, code, json["data"]);
  }
  if (isObj(json) && isObj(json["error"]) && typeof json["error"]["code"] === "string") {
    throw new L01Error("http", status, json["error"]["code"]);
  }
  throw new L01Error("contract", status, "unexpected_error_body");
}

/** Unwrap `{data, demo}` and require a receipt shape. */
export function receiptOf(body: unknown, status: number): OperationReceipt {
  const data = isObj(body) ? body["data"] : undefined;
  if (!isReceipt(data)) throw new L01Error("contract", status, "unexpected_receipt");
  return data;
}

export function directoryPageOf(body: unknown, status: number): ClientDirectoryPage {
  if (
    !isObj(body) ||
    !Array.isArray(body["data"]) ||
    !(body["next_cursor"] === null || typeof body["next_cursor"] === "string") ||
    typeof body["demo"] !== "boolean" ||
    !body["data"].every(
      (e) =>
        isObj(e) && typeof e["client_id"] === "string" && typeof e["display_name"] === "string",
    )
  ) {
    throw new L01Error("contract", status, "unexpected_directory_page");
  }
  return body as unknown as ClientDirectoryPage;
}

/** Follow next_cursor unchanged until null. Guards against a repeated cursor. */
export async function listAllClients(t: L01Transport, tenant: Uuid, limit?: number) {
  const out: ClientDirectoryPage["data"] = [];
  const seen = new Set<string>();
  let after: Uuid | undefined;
  for (;;) {
    const page = await t.listClients(tenant, {
      ...(limit ? { limit } : {}),
      ...(after ? { after } : {}),
    });
    out.push(...page.data);
    if (page.next_cursor === null) return out;
    if (seen.has(page.next_cursor)) throw new L01Error("contract", 200, "repeated_cursor");
    seen.add(page.next_cursor);
    after = page.next_cursor;
  }
}

/* ---------- Idempotent resend design (inactive until live integration) ---------- */

/** Captured BEFORE sending so the identical request can be resent after a lost response. */
export interface PendingOperation {
  request: OperationRequest;
  tenant: Uuid;
  client: Uuid;
  principal: string;
  createdAt: string;
}

/** Operations that must never be retried automatically. */
export const NO_AUTO_RETRY: readonly OperationName[] = ["intervene", "undo", "discover_company"];

/** Policy: no automatic retries at all; resend is always an explicit user action. */
export const shouldAutoRetry = (_op: OperationName): false => false;

export function preparePending(
  tenant: Uuid,
  client: Uuid,
  principal: string,
  request: Omit<OperationRequest, "request_id">,
  newId: () => string = () => crypto.randomUUID(),
): PendingOperation {
  return {
    tenant,
    client,
    principal,
    createdAt: new Date().toISOString(),
    request: { ...request, request_id: newId() } as OperationRequest,
  };
}

/**
 * An explicit resend is only valid with the same request_id, operation,
 * arguments and principal. Anything else must be a NEW request (new id),
 * otherwise L01 answers 409 request_conflict.
 */
export function canResendIdentically(p: PendingOperation, principal: string): boolean {
  return p.principal === principal;
}

