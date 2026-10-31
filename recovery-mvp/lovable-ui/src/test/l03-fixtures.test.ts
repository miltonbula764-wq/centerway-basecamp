// L03-OFFLINE: replay every case of the Codex L03-PREP capture (l03-prep-v1)
// through FixtureTransport + journey-mapper. Offline only; fetch is trapped.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import {
  FixtureMismatchError,
  FixtureTransport,
  type FixtureBundle,
  type FixtureCase,
} from "@/data/fixture-transport";
import { businessStatusOf, mapJourney, validateJourneyEnvelope } from "@/data/journey-mapper";
import { L01Error, classifyResponse, listAllClients } from "@/data/transport";
import { errorKindOf } from "@/components/cw/states";
import type { ClientJourney } from "@/domain/f06";
import type { OperationReceipt, OperationRequest } from "@/domain/l01";

const DIR = join(__dirname, "fixtures/l03-prep-v1");
const raw = readFileSync(join(DIR, "capture.json"), "utf8");
const bundle = JSON.parse(raw) as FixtureBundle;
const byId = new Map(bundle.cases.map((c) => [c.id, c]));
const get = (id: string) => byId.get(id)!;

const TA = "a1000000-0000-0000-0000-000000000001";
const TB = "b1000000-0000-0000-0000-000000000001";
const CA = "a2000000-0000-0000-0000-000000000001";

/** Expected HTTP / receipt / business columns from CASE_MATRIX.md (independent of capture.json). */
const matrix = new Map<string, { http: string; receipt: string; business: string }>();
for (const line of readFileSync(join(DIR, "CASE_MATRIX.md"), "utf8").split("\n")) {
  const m = /^\| `([^`]+)` \| \w+ \| ([^|]+) \| ([^|]+) \| ([^|]+) \| PASS \|$/.exec(line.trim());
  if (m) matrix.set(m[1]!, { http: m[2]!.trim(), receipt: m[3]!.trim(), business: m[4]!.trim() });
}

let fetchSpy: ReturnType<typeof vi.fn>;
beforeAll(() => {
  fetchSpy = vi.fn(() => Promise.reject(new Error("network forbidden in L03-OFFLINE")));
  vi.stubGlobal("fetch", fetchSpy);
});
afterAll(() => {
  expect(fetchSpy).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});

const parsePath = (p: string) => /^\/v1\/tenants\/([^/]+)\/clients\/([^/?]+)/.exec(p)!;
const queryOf = (p: string) => {
  const q = new URLSearchParams(p.split("?")[1] ?? "");
  return {
    ...(q.has("limit") ? { limit: Number(q.get("limit")) } : {}),
    ...(q.has("after") ? { after: q.get("after")! } : {}),
  };
};

async function rejection(p: Promise<unknown>): Promise<L01Error> {
  try {
    await p;
  } catch (e) {
    expect(e).toBeInstanceOf(L01Error);
    return e as L01Error;
  }
  throw new Error("expected an L01Error");
}

/** Replay a case through the public transport method that matches its route. */
async function replay(c: FixtureCase, t = new FixtureTransport(bundle)) {
  t.expect(c.id, c.actor);
  const { method, path, json } = c.request;
  if (method === "POST" && path === "/v1/sessions") return t.createSession(json as never);
  if (path === "/v1/session") return method === "DELETE" ? t.deleteSession() : t.getSession();
  if (/\/clients\/[^/]+\/journey$/.test(path)) {
    const m = parsePath(path);
    return t.getJourney(m[1]!, m[2]!);
  }
  if (/\/operations$/.test(path)) {
    const m = parsePath(path);
    // Non-envelope bodies (invalid-envelope-422) go through the raw replay.
    if (
      json &&
      Object.keys(json).some((k) => !["request_id", "operation", "arguments"].includes(k))
    )
      return t.request("POST", path, json);
    return t.operate(m[1]!, m[2]!, json as unknown as OperationRequest);
  }
  if (/^\/v1\/tenants\/[^/]+\/clients(\?|$)/.test(path))
    return t.listClients(path.split("/")[3]!, queryOf(path));
  return t.request(method, path, json);
}

/* ---------------- per-case behaviour ---------------- */

type Check = (c: FixtureCase) => Promise<void>;

const sessionCreated: Check = async (c) => {
  const s = await replay(c);
  expect(c.response!.status).toBe(201);
  expect(s).toMatchObject({ token_type: "Bearer", expires_in: 900, demo: false });
  // Placeholder, never a usable bearer; the request password is a placeholder too.
  expect((s as { access_token: string }).access_token).toMatch(
    new RegExp(`^<SESSION:${c.actor}:\\d+>$`),
  );
  expect(c.request.json).toEqual({ username: c.actor, password: `<PASSWORD:${c.actor}>` });
};

const OPS_ALL = [
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
];
const sessionInfo: Check = async (c) => {
  const s = (await replay(c)) as {
    username: string;
    principal: string;
    clients: Record<string, string[]>;
    operations: string[];
    company_tenants: string[];
  };
  expect(s.username).toBe(c.actor);
  expect(s.principal).toBe(`http_${c.actor}`);
  expect(s.company_tenants).toEqual([]);
  if (c.actor === "bob") {
    expect(Object.keys(s.clients)).toEqual([TB]);
    expect(s.operations).toEqual(OPS_ALL);
  }
  if (c.actor === "alice") {
    expect(s.clients).toEqual({ [TA]: [CA] });
    expect(s.operations).toEqual(OPS_ALL);
  }
  if (c.actor === "reviewer") {
    expect(s.operations).toEqual(["append_investigation", "investigate"]);
    expect(s.operations).not.toContain("intervene");
  }
  if (c.actor === "reader") {
    expect(s.operations).toEqual([]);
    // Grant of A2 happened between reader-1 and reader-2 (private config): two distinct states.
    expect(s.clients[TA]).toHaveLength(c.id === "session-reader-1" ? 1 : 2);
  }
};

const journeyCheck: Check = async (c) => {
  const j = (await replay(c)) as ClientJourney;
  expect(j.contract_version).toBe("f06-v1");
  expect(j.causal_attribution).toBe("not_established");
  expect(j.authorization_basis).toBe("engine_checks_required_at_execution");
  const vm = mapJourney(j, null);
  expect(vm.id).toBe(CA);
  expect(vm.demo).toBeNull(); // no demo metadata injected for capture data
  expect(vm.displayName).toBe(`Cliente ${CA.slice(0, 8)}`); // journey carries no name
  expect(vm.causalAttribution).toBe("not_established");
  expect(vm.receipts).toHaveLength(j.operations.length);
  expect(vm.workItems).toHaveLength(j.work_items.length);
  for (const r of vm.receipts) expect(["completed", "error"]).toContain(r.transportStatus);
  for (const rec of vm.recoveries)
    expect(
      rec.status === null ||
        /^(recuperacao_completa|recuperacao_parcial|ausencia_de_recuperacao|resultado_inconclusivo)$/.test(
          rec.status,
        ),
    ).toBe(true);
  JOURNEY_CHECKPOINT[c.id]!(j, vm);
};

type VM = ReturnType<typeof mapJourney>;
const JOURNEY_CHECKPOINT: Record<string, (j: ClientJourney, vm: VM) => void> = {
  "journey-initial": (j) => {
    expect(j.operations).toHaveLength(0);
    expect(j.detections).toHaveLength(0);
    expect(j.decisions).toHaveLength(0);
  },
  "journey-after-append_value-1": (j) => {
    expect(j.operations.map((o) => o.operation)).toEqual(["append_value"]);
  },
  "journey-after-detect-1": (j) => {
    expect(j.detections.some((d) => d.state === "deterioracao_demonstrada")).toBe(true);
    expect(j.investigations).toHaveLength(0);
  },
  "journey-after-open_investigation-1": (j) => {
    expect(j.investigations).toHaveLength(1);
    expect(j.investigations[0]!.result).toBeNull();
  },
  "journey-after-investigate-1": (_j, vm) => {
    expect(vm.investigations[0]!.report).not.toBeNull();
  },
  "journey-after-intervene-1": (_j, vm) => {
    expect(vm.decisions.map((d) => d.status)).toEqual(["blocked"]);
    expect(vm.decisions[0]!.executions).toHaveLength(0);
  },
  "journey-after-investigate-2": (j) => {
    expect(j.decisions).toHaveLength(1);
  },
  "journey-after-intervene-2": (j, vm) => {
    expect(vm.decisions.map((d) => d.status)).toEqual(["blocked", "executed"]);
    expect(j.executions).toHaveLength(1);
    expect(j.recovery_plans).toHaveLength(0); // executed ≠ recovered
  },
  "get-journey-09": (j) => {
    expect(j).toEqual(get("journey-after-intervene-2").response!.json!["data"]);
  },
  "journey-after-evaluate_recovery-1": (_j, vm) => {
    const r = vm.recoveries[0]!;
    expect(r.status).toBe("resultado_inconclusivo");
    expect(r.improvementObserved).toBeNull(); // null stays unknown, never false/0
    expect(r.executionSucceeded).toBe(true);
  },
  "journey-after-evaluate_recovery-2": (j, vm) => {
    const r = vm.recoveries[0]!;
    expect(r).toMatchObject({
      status: "recuperacao_completa",
      executionSucceeded: true,
      improvementObserved: true,
      minimumMet: true,
      before: 8,
      after: 15,
      minimum: 15,
    });
    expect(j.recovery_plans[0]!.result!.causal_attribution).toBe("not_established");
    expect(j.recovery_plans[0]!.result!.independent_verification).toBe("not_established");
    // Historic guidance coexists with later recovery; it is not deleted.
    expect(vm.workItems.map((w) => w.next)).toContain("review_execution_blocker");
  },
  "journey-with-error-receipt": (_j, vm) => {
    const last = vm.receipts.at(-1)!;
    expect(last).toMatchObject({ transportStatus: "error", businessStatus: "engine_rejected" });
    expect(JSON.stringify(vm)).not.toContain("23502"); // receipts VM never carries sqlstate
  },
};

const receiptCheck: Check = async (c) => {
  const r = (await replay(c)) as OperationReceipt;
  const req = c.request.json as unknown as OperationRequest;
  expect(r.status).toBe("completed");
  expect(r.request_id).toBe(req.request_id);
  expect(r.operation).toBe(req.operation);
  expect(r.arguments).toEqual(req.arguments);
  expect(r.actor).toBe(`http_${c.actor}`);
  // Business status only from result — compared against the independent matrix column.
  const expected = matrix.get(c.id)!.business;
  if (expected !== "—") expect(businessStatusOf(r.result)).toBe(expected);
  if (["detect", "investigate", "intervene", "evaluate_recovery"].includes(r.operation))
    expect(expected).not.toBe("—");
  RECEIPT_EXTRA[c.id]?.(r);
};

const res = (r: OperationReceipt) => r.result as Record<string, unknown>;
const RECEIPT_EXTRA: Record<string, (r: OperationReceipt) => void> = {
  "intervene-01": (r) => {
    expect(res(r)).toMatchObject({
      status: "blocked",
      execution_id: null,
      value_recovery: "not_evaluated",
      reason: "uncertain_investigation",
    });
  },
  "intervene-02": (r) => {
    expect(res(r)["status"]).toBe("executed");
    expect(res(r)["execution_id"]).toEqual(expect.any(String));
  },
  "evaluate_recovery-01": (r) => {
    const inner = res(r)["result"] as Record<string, unknown>;
    expect(inner["status"]).toBe("resultado_inconclusivo");
    expect(inner["improvement_observed"]).toBeNull();
    expect(inner["causal_attribution"]).toBe("not_established");
  },
  "evaluate_recovery-02": (r) => {
    const inner = res(r)["result"] as Record<string, unknown>;
    expect(inner).toMatchObject({
      status: "recuperacao_completa",
      execution_succeeded: true,
      improvement_observed: true,
      minimum_met: true,
      causal_attribution: "not_established",
      independent_verification: "not_established",
    });
  },
  "intervention-idempotent-replay": (r) => {
    expect(r).toEqual(get("intervene-02").response!.json!["data"]);
  },
};

const directoryCheck: Check = async (c) => {
  const p = (await replay(c)) as {
    data: { client_id: string; display_name: string }[];
    next_cursor: string | null;
    demo: boolean;
  };
  expect(p.demo).toBe(false); // guards on; data still synthetic
  for (const e of p.data) expect(e.display_name).toMatch(/^SYNTHETIC /);
  const extra: Record<string, () => void> = {
    "directory-alice": () => {
      expect(p.data.map((e) => e.client_id)).toEqual([CA]);
      expect(p.next_cursor).toBeNull();
    },
    "directory-reviewer": () => {
      expect(p.data.map((e) => e.client_id)).toEqual([CA]);
    },
    "directory-reader": () => {
      expect(p.data.map((e) => e.client_id)).toEqual([CA]);
    },
    "directory-bob": () => {
      expect(p.data.every((e) => e.client_id.startsWith("b2"))).toBe(true);
    },
    "directory-page-1": () => {
      expect(p.data).toHaveLength(1);
      expect(p.next_cursor).toBe(CA);
    },
    "directory-page-2": () => {
      expect(queryOf(c.request.path).after).toBe(
        get("directory-page-1").response!.json!["next_cursor"],
      );
      expect(p.next_cursor).toBeNull();
    },
    "directory-page-empty": () => {
      expect(p.data).toEqual([]);
      expect(p.next_cursor).toBeNull();
    },
  };
  extra[c.id]!();
};

const httpError =
  (status: number, code: string, ui: string): Check =>
  async (c) => {
    const e = await rejection(replay(c));
    expect(e.kind).toBe("http");
    expect(e.status).toBe(status);
    expect(e.code).toBe(code);
    expect(e.receipt).toBeUndefined(); // pre-engine: no receipt
    expect(errorKindOf(e)).toBe(ui);
  };

const CHECKS: { match: (id: string) => boolean; check: Check }[] = [
  { match: (id) => id.startsWith("post-sessions-"), check: sessionCreated },
  { match: (id) => id.startsWith("session-"), check: sessionInfo },
  { match: (id) => id in JOURNEY_CHECKPOINT, check: journeyCheck },
  {
    match: (id) =>
      /^(append_value|detect|open_investigation|append_investigation|investigate|intervene|plan_recovery|evaluate_recovery)-\d+$/.test(
        id,
      ) || id === "intervention-idempotent-replay",
    check: receiptCheck,
  },
  {
    match: (id) => id.startsWith("directory-") && id !== "directory-invalid-limit-422",
    check: directoryCheck,
  },
  {
    match: (id) => ["authentication-required-401"].includes(id),
    check: httpError(401, "authentication_required", "401"),
  },
  {
    match: (id) => ["changed-scope-invalidates-session-401", "revoked-session-401"].includes(id),
    check: httpError(401, "session_expired_or_invalid", "401"),
  },
  {
    match: (id) =>
      [
        "bob-denied-company-a-403",
        "alice-denied-company-b-403",
        "reader-denied-client-403",
      ].includes(id),
    check: httpError(403, "forbidden", "403"),
  },
  {
    match: (id) =>
      ["reader-denied-intervention-403", "reviewer-denied-intervention-403"].includes(id),
    check: httpError(403, "operation_forbidden", "403"),
  },
  {
    match: (id) => id === "idempotency-conflict-409",
    check: async (c) => {
      await httpError(409, "request_conflict", "409")(c);
      const prev = get("intervene-02").request.json as Record<string, unknown>;
      expect((c.request.json as Record<string, unknown>)["request_id"]).toBe(prev["request_id"]);
      expect((c.request.json as Record<string, unknown>)["arguments"]).not.toEqual(
        prev["arguments"],
      );
    },
  },
  {
    match: (id) => ["invalid-envelope-422", "directory-invalid-limit-422"].includes(id),
    check: httpError(422, "invalid_parameters", "422"),
  },
  {
    match: (id) => id === "engine-error-receipt-422",
    check: async (c) => {
      const e = await rejection(replay(c));
      expect(e.kind).toBe("receipt"); // engine rejection with a persisted receipt
      expect(e.status).toBe(422);
      expect(e.code).toBe("engine_rejected");
      expect(e.receipt!.status).toBe("error");
      expect(e.message).not.toMatch(/\d{5}/); // no raw SQLSTATE in the message
      expect(errorKindOf(e)).toBe("422");
    },
  },
  { match: (id) => id === "unknown-route-404", check: httpError(404, "http_404", "404") },
  {
    match: (id) => id === "database-unavailable-503",
    check: httpError(503, "database_unavailable", "503"),
  },
  {
    match: (id) => id === "api-unavailable-503",
    check: httpError(503, "gateway_unavailable", "503"),
  },
  {
    match: (id) => id === "logout-204",
    check: async (c) => {
      expect(c.response).toEqual({ status: 204, json: null });
      await expect(replay(c)).resolves.toBeUndefined();
    },
  },
  {
    match: (id) => id === "network-failure",
    check: async (c) => {
      const e = await rejection(replay(c));
      expect(e).toMatchObject({ kind: "network", status: null, code: "connection_refused" });
      expect(errorKindOf(e)).toBe("network"); // not an invented 503
    },
  },
];

/* ---------------- suites ---------------- */

describe("L03-PREP bundle integrity", () => {
  it("header, provenance and 71 unique case ids", () => {
    expect(bundle).toMatchObject({
      fixture_version: "l03-prep-v1",
      synthetic_only: true,
      source: "real-local-c03-https-api",
      sanitization: "typed-placeholders-v1",
      base_commit: "eeae52ef4d1fbf3bdc524299203098fe75f6badd",
    });
    expect(bundle.contracts["api/openapi.json"]).toBe(
      "83196d58e29affcaf635de68ce67975885ce4b5c5f4ec4c9221fd9317305db95",
    );
    expect(bundle.cases).toHaveLength(71);
    expect(new Set(bundle.cases.map((c) => c.id)).size).toBe(71);
  });

  it("every case follows bundle.schema.json structure", () => {
    for (const c of bundle.cases) {
      expect(Object.keys(c).sort()).toEqual([
        "actor",
        "id",
        "request",
        "response",
        "transport_error",
      ]);
      expect(["alice", "reviewer", "reader", "bob"]).toContain(c.actor);
      expect(["GET", "POST", "DELETE"]).toContain(c.request.method);
      expect(c.request.path).toMatch(/^\/v1\//);
      if (c.response)
        expect([200, 201, 204, 401, 403, 404, 409, 422, 503]).toContain(c.response.status);
      expect(c.response === null).toBe(c.transport_error === "connection_refused");
    }
  });

  it("contains no secrets: only typed placeholders for passwords/tokens, no DSN, no email", () => {
    for (const m of raw.matchAll(/"(password|access_token)":\s*"([^"]*)"/g))
      expect(m[2]).toMatch(/^<(PASSWORD|SESSION):[a-z]+(:\d+)?>$/);
    expect(raw).not.toMatch(/postgres(ql)?:\/\//i);
    expect(raw).not.toMatch(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/);
    expect(raw).not.toMatch(/Bearer\s+[A-Za-z0-9._-]{16,}/);
    expect(raw).not.toMatch(/-----BEGIN/);
  });

  it("CASE_MATRIX lists exactly the same 71 cases with matching HTTP/receipt columns", () => {
    expect(matrix.size).toBe(71);
    for (const c of bundle.cases) {
      const row = matrix.get(c.id)!;
      expect(row, c.id).toBeDefined();
      expect(row.http).toBe(
        c.response ? String(c.response.status) : "sem HTTP (connection_refused)",
      );
      const d = (c.response?.json?.["data"] ?? null) as Record<string, unknown> | null;
      const receipt = d && typeof d === "object" && "request_id" in d ? String(d["status"]) : "—";
      expect(row.receipt).toBe(receipt);
    }
  });

  it("every case is claimed by exactly one behaviour check", () => {
    for (const c of bundle.cases) expect(CHECKS.filter((k) => k.match(c.id)).length, c.id).toBe(1);
  });
});

describe("L03-PREP: replay each captured case offline", () => {
  it.each(bundle.cases.map((c) => [c.id, c] as const))("%s", async (_id, c) => {
    await CHECKS.find((k) => k.match(c.id))!.check(c);
  });
});

describe("L03-PREP: sequence-level behaviour", () => {
  it("journey operations only grow along the captured sequence (history preserved)", () => {
    const counts = bundle.cases
      .filter(
        (c) =>
          c.request.method === "GET" &&
          c.request.path.endsWith(`/clients/${CA}/journey`) &&
          c.response?.status === 200,
      )
      .map((c) => (c.response!.json!["data"] as ClientJourney).operations.length);
    expect(counts.length).toBe(Object.keys(JOURNEY_CHECKPOINT).length); // 12 captured 200 journeys
    for (let i = 1; i < counts.length; i++)
      expect(counts[i]!).toBeGreaterThanOrEqual(counts[i - 1]!);
  });

  it("follows next_cursor across pages via listAllClients and stops at null", async () => {
    const t = new FixtureTransport(bundle);
    const order = ["directory-page-1", "directory-page-2"];
    const wrapped = {
      ...t,
      mode: t.mode,
      listClients: (tenant: string, p?: { limit?: number; after?: string }) => {
        t.expect(order.shift()!);
        return t.listClients(tenant, p);
      },
    } as unknown as FixtureTransport;
    const all = await listAllClients(wrapped, TA, 1);
    expect(all.map((e) => e.client_id)).toEqual([CA, "a2000000-0000-0000-0000-000000000002"]);
    expect(order).toEqual([]);
  });
});

describe("FixtureTransport fails explicitly outside the capture", () => {
  it("rejects a call without an armed case (no fallback to mock data)", async () => {
    await expect(new FixtureTransport(bundle).getSession()).rejects.toBeInstanceOf(
      FixtureMismatchError,
    );
  });
  it("rejects a different path than the armed case", async () => {
    const t = new FixtureTransport(bundle).expect("journey-initial");
    await expect(t.getJourney(TA, "a2000000-0000-0000-0000-000000000002")).rejects.toBeInstanceOf(
      FixtureMismatchError,
    );
  });
  it("rejects a body that differs from the capture", async () => {
    const c = get("intervene-02");
    const req = {
      ...(c.request.json as unknown as OperationRequest),
      request_id: "00000000-0000-4000-8000-0000000000ff",
    };
    await expect(
      new FixtureTransport(bundle).expect(c.id).operate(TA, CA, req),
    ).rejects.toBeInstanceOf(FixtureMismatchError);
  });
  it("rejects the wrong actor and unknown ids", () => {
    expect(() => new FixtureTransport(bundle).expect("intervene-02", "reader")).toThrow(
      FixtureMismatchError,
    );
    expect(() => new FixtureTransport(bundle).expect("not-a-case")).toThrow(FixtureMismatchError);
  });
  it("an armed case is consumed once", async () => {
    const t = new FixtureTransport(bundle).expect("session-alice-1");
    await t.getSession();
    await expect(t.getSession()).rejects.toBeInstanceOf(FixtureMismatchError);
  });
});

describe("contract guards", () => {
  it("rejects an unsupported journey version or missing collections as a contract error", () => {
    const ok = get("journey-initial").response!.json!;
    expect(() =>
      validateJourneyEnvelope({
        ...ok,
        data: { ...(ok["data"] as object), contract_version: "f07" },
      }),
    ).toThrow(/journey_version_unsupported/);
    const { work_items: _w, ...noWork } = ok["data"] as Record<string, unknown>;
    expect(() => validateJourneyEnvelope({ ...ok, data: noWork })).toThrow(
      /journey_missing_work_items/,
    );
    expect(() =>
      validateJourneyEnvelope({
        ...ok,
        data: { ...(ok["data"] as object), causal_attribution: "established" },
      }),
    ).toThrow(/causal/);
  });
  it("HTTP 200 never becomes business success by itself; 204 is not parsed", () => {
    expect(classifyResponse(204, null)).toBeUndefined();
    expect(() => classifyResponse(200, null)).toThrow(L01Error);
    const blocked = get("intervene-01").response!;
    expect(businessStatusOf((blocked.json!["data"] as OperationReceipt).result)).toBe("blocked");
  });
  it("fixture transport source never calls fetch", () => {
    const src = readFileSync(join(__dirname, "../data/fixture-transport.ts"), "utf8");
    expect(src).not.toMatch(/\bfetch\s*\(/);
  });
});

