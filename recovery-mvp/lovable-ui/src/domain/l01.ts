// L01 HTTP transport contract (recovery-mvp/api/README.md + openapi.json, branch
// recovery-mvp/l01-authenticated-api). Types only — L02.2 never calls the network.

export type Uuid = string;
/** ISO-8601 instant with explicit offset. */
export type Instant = string;

/** POST /v1/sessions request. Never persisted by the UI. */
export interface LoginRequest {
  username: string;
  password: string;
}

/** POST /v1/sessions → 201. Token must live in memory only. */
export interface SessionCreated {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
  demo: boolean;
}

/** GET /v1/session → 200. Scopes are UX hints; the server decides. */
export interface SessionInfo {
  username: string;
  principal: string;
  /** tenant uuid → authorised client uuids */
  clients: Record<Uuid, Uuid[]>;
  operations: OperationName[];
  company_tenants: Uuid[];
  demo?: boolean;
}

export const OPERATION_NAMES = [
  "append_value",
  "detect",
  "discover_company",
  "open_investigation",
  "append_investigation",
  "investigate",
  "intervene",
  "undo",
  "plan_recovery",
  "evaluate_recovery",
] as const;
export type OperationName = (typeof OPERATION_NAMES)[number];

/** Argument keys per operation (ORCHESTRATION.md). Values validated by the engines. */
export interface OperationArguments {
  append_value: { kind: string; id: Uuid; expected_revision: number; reason: string; data: unknown };
  detect: { contract_id: Uuid; revisions: number[]; as_of: Instant; required_periods: number };
  discover_company: { as_of: Instant };
  open_investigation: { id: Uuid; detection_id: Uuid; contract_revision: number; question: string };
  append_investigation: { investigation_id: Uuid; kind: string; id: Uuid; expected_revision: number; reason: string; data: unknown };
  investigate: { investigation_id: Uuid; as_of: Instant };
  intervene: { investigation_id: Uuid; report_id: Uuid };
  undo: { execution_id: Uuid };
  plan_recovery: { id: Uuid; decision_id: Uuid; pre_revision: number; post_revision: number; reason: string };
  evaluate_recovery: { plan_id: Uuid; as_of: Instant };
}

/** POST /v1/tenants/{t}/clients/{c}/operations body. */
export interface OperationRequest<O extends OperationName = OperationName> {
  request_id: Uuid;
  operation: O;
  arguments: OperationArguments[O];
}

/**
 * F06 operation_receipts envelope. `status` is the TRANSPORT/porta level:
 * "completed" only means the delegated engine returned — the business result
 * inside `result` may still be blocked, failed or inconclusive.
 */
export interface OperationReceipt {
  tenant_id: Uuid;
  client_id: Uuid;
  request_id: Uuid;
  operation: OperationName;
  arguments: unknown;
  status: "completed" | "error";
  /** Engine result (schema per engine) or {sqlstate, code:"engine_rejected"} on error. */
  result: unknown;
  actor: string;
  recorded_at: Instant;
}

export interface DataEnvelope<T> {
  data: T;
  demo: boolean;
}

/** HTTP-level error body (pre-engine rejection: no receipt was stored). */
export interface ErrorEnvelope {
  error: { code: string };
}

/** Result body of an error receipt. `sqlstate` is diagnostic only — never UI copy. */
export interface EngineRejectedResult {
  code: "engine_rejected";
  sqlstate: string;
}

/** GET /v1/tenants/{tenant}/clients item (openapi c02-v1 ClientDirectoryPage). Render as text only. */
export interface ClientDirectoryEntry {
  client_id: Uuid;
  display_name: string;
}

/** Keyset page: no totals, no snapshot. `data: []` is not an error. */
export interface ClientDirectoryPage {
  data: ClientDirectoryEntry[];
  /** Pass unchanged as `after`; stop at null. */
  next_cursor: Uuid | null;
  /** `false` only enables HTTPS/PG guards — it never makes synthetic data real. */
  demo: boolean;
}

/** Query params: limit 1..100 (default 50), exclusive UUID cursor. */
export interface ListClientsParams {
  limit?: number;
  after?: Uuid;
}

export type HttpStatus = 400 | 401 | 403 | 404 | 409 | 413 | 415 | 422 | 429 | 500 | 503;

