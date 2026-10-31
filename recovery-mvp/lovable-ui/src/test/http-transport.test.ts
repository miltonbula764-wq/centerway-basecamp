import { describe, expect, it, vi } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import {
  HttpTransport,
  HttpTransportConfigError,
  parseBaseUrl,
  type FetchLike,
} from "@/data/http-transport";
import { L01Error } from "@/data/transport";
import type { FixtureBundle, FixtureCase } from "@/data/fixture-transport";

const bundle = JSON.parse(
  readFileSync(join(__dirname, "fixtures/l03-prep-v1/capture.json"), "utf8"),
) as FixtureBundle;
const byId = new Map(bundle.cases.map((c) => [c.id, c]));
const kase = (id: string) => byId.get(id)!;
const BASE = "https://api.centerway.test";
const T = "11111111-1111-4111-8111-111111111111";
const C = "22222222-2222-4222-8222-222222222222";
const RID = "33333333-3333-4333-8333-333333333333";

function res(status: number, json: unknown) {
  return new Response(status === 204 || json === null ? null : JSON.stringify(json), { status });
}
type Call = { url: string; init: RequestInit };
function fake(queue: (Response | Error)[]) {
  const calls: Call[] = [];
  const fn: FetchLike = async (url, init) => {
    calls.push({ url, init });
    const next = queue.shift();
    if (!next) throw new Error("unexpected extra fetch");
    if (next instanceof Error) throw next;
    return next;
  };
  return { fn, calls };
}
const fromCase = (c: FixtureCase) => res(c.response!.status, c.response!.json);
const LOGIN = () =>
  res(201, { access_token: "secret-token", token_type: "Bearer", expires_in: 900, demo: true });

async function logged(queue: (Response | Error)[], now = () => 0) {
  const f = fake([LOGIN(), ...queue]);
  const t = new HttpTransport({ baseUrl: BASE, fetch: f.fn, now });
  await t.createSession({ username: "u", password: "p" });
  return { t, calls: f.calls };
}
const err = async (p: Promise<unknown>) => {
  try {
    await p;
  } catch (e) {
    return e as L01Error;
  }
  throw new Error("expected rejection");
};

describe("HttpTransport config", () => {
  it.each([
    [undefined, "base_url_missing"],
    ["", "base_url_missing"],
    ["not a url", "base_url_invalid"],
    ["http://api.x.test", "base_url_not_https"],
    ["https://localhost:8443", "base_url_localhost"],
    ["https://127.0.0.1", "base_url_localhost"],
    ["https://u:p@api.x.test", "base_url_has_credentials"],
    ["https://api.x.test/?a=1", "base_url_has_query"],
  ])("rejects %s", (url, code) => {
    expect(() => parseBaseUrl(url)).toThrow(new HttpTransportConfigError(code));
  });
  it("allows localhost only when explicit and requires injected fetch", () => {
    expect(parseBaseUrl("https://localhost:8443/", true)).toBe("https://localhost:8443");
    expect(() => new HttpTransport({ baseUrl: BASE } as never)).toThrow("fetch_missing");
  });
  it("makes no request on construction", () => {
    const f = vi.fn();
    new HttpTransport({ baseUrl: BASE, fetch: f });
    expect(f).not.toHaveBeenCalled();
  });
});

describe("HttpTransport methods (replaying captured responses)", () => {
  it("login keeps bearer in memory only and never returns it", async () => {
    const f = fake([fromCase(kase("post-sessions-01")), fromCase(kase("session-reader-1"))]);
    const t = new HttpTransport({ baseUrl: BASE, fetch: f.fn });
    const s = await t.createSession({ username: "u", password: "p" });
    expect(s.access_token).toBe("[memory-only]");
    expect(f.calls[0]!.init.headers).not.toHaveProperty("Authorization");
    expect(f.calls[0]!.init.redirect).toBe("error");
    expect(f.calls[0]!.init.credentials).toBe("omit");
    const info = await t.getSession();
    expect(typeof info.principal).toBe("string");
    expect((f.calls[1]!.init.headers as Record<string, string>)["Authorization"]).toMatch(
      /^Bearer .+/,
    );
    expect(JSON.stringify(t)).not.toContain(
      (kase("post-sessions-01").response!.json as { access_token: string }).access_token,
    );
  });

  it("logout accepts 204 without JSON and clears the token", async () => {
    const { t, calls } = await logged([fromCase(kase("logout-204"))]);
    await t.deleteSession();
    expect(calls[1]!.init.method).toBe("DELETE");
    expect(t.hasSession).toBe(false);
    expect((await err(t.getSession())).code).toBe("session_expired_locally");
  });

  it("listClients builds cursor/limit query and validates limit 1..100", async () => {
    const { t, calls } = await logged([fromCase(kase("directory-page-1"))]);
    const page = await t.listClients(T, { limit: 2, after: C });
    expect(calls[1]!.url).toBe(`${BASE}/v1/tenants/${T}/clients?limit=2&after=${C}`);
    expect(Array.isArray(page.data)).toBe(true);
    for (const bad of [0, 101, 1.5])
      expect((await err(t.listClients(T, { limit: bad }))).code).toBe("invalid_limit");
    expect(calls.length).toBe(2);
  });

  it("getJourney validates the envelope and keeps causal_attribution not_established", async () => {
    const c = kase("journey-initial");
    const [, , tenant, , client] = c.request.path.split("/").slice(1);
    const { t } = await logged([fromCase(c)]);
    const j = await t.getJourney(tenant!, client!);
    expect(JSON.stringify(j)).toContain("not_established");
  });

  it("operate requires request_id, sends one attempt, HTTP 200 is not business success", async () => {
    const c = kase("intervene-01");
    const parts = c.request.path.split("/");
    const { t, calls } = await logged([fromCase(c)]);
    const req = c.request.json as never;
    const r = await t.operate(parts[3]!, parts[5]!, req);
    expect(r.status).toBe("completed");
    expect(JSON.stringify(r.result)).toContain("blocked");
    expect(JSON.parse(calls[1]!.init.body as string)).toEqual(c.request.json);
    expect((await err(t.operate(T, C, { operation: "undo", arguments: {} } as never))).code).toBe(
      "request_id_required",
    );
    expect(calls.length).toBe(2);
  });
});

describe("HttpTransport failures", () => {
  const op = { request_id: RID, operation: "undo", arguments: { execution_id: RID } } as const;

  it.each([
    ["changed-scope-invalidates-session-401", 401],
    ["bob-denied-company-a-403", 403],
    ["unknown-route-404", 404],
    ["database-unavailable-503", 503],
  ])("%s surfaces as http %i", async (id, status) => {
    const { t } = await logged([fromCase(kase(id))]);
    const e = await err(t.getJourney(T, C));
    expect(e).toBeInstanceOf(L01Error);
    expect([e.kind, e.status]).toEqual(["http", status]);
  });

  it("401 drops the in-memory token", async () => {
    const { t } = await logged([fromCase(kase("revoked-session-401"))]);
    await err(t.getSession());
    expect(t.hasSession).toBe(false);
  });

  it("409 conflict and 422 pre-engine are http; 422 with receipt is kind receipt without SQLSTATE in message", async () => {
    const { t } = await logged([
      fromCase(kase("idempotency-conflict-409")),
      fromCase(kase("invalid-envelope-422")),
      fromCase(kase("engine-error-receipt-422")),
    ]);
    expect((await err(t.operate(T, C, op))).status).toBe(409);
    const pre = await err(t.operate(T, C, op));
    expect([pre.kind, pre.status, pre.receipt]).toEqual(["http", 422, undefined]);
    const rec = await err(t.operate(T, C, op));
    expect(rec.kind).toBe("receipt");
    expect(rec.receipt?.status).toBe("error");
    expect(rec.message).not.toMatch(/sqlstate|\b[0-9A-Z]{5}\b.*sql/i);
    expect(rec.code).toBe("engine_rejected");
  });

  it("network failure is not an invented 503 and is not retried", async () => {
    const { t, calls } = await logged([new TypeError("Failed to fetch")]);
    const e = await err(t.operate(T, C, op));
    expect([e.kind, e.status]).toEqual(["network", null]);
    expect(calls.length).toBe(2);
  });

  it("invalid bodies and redirects are contract errors", async () => {
    const { t } = await logged([
      new Response("<html>", { status: 200 }),
      res(200, { data: [{ nope: 1 }], next_cursor: null, demo: true }),
      res(302, null),
      res(500, { weird: true }),
    ]);
    expect((await err(t.getSession())).kind).toBe("contract");
    expect((await err(t.listClients(T))).code).toBe("unexpected_directory_page");
    expect((await err(t.getSession())).code).toBe("unexpected_redirect");
    expect((await err(t.getSession())).code).toBe("unexpected_error_body");
  });

  it("bad login body is rejected and stores nothing", async () => {
    const f = fake([res(201, { token_type: "Bearer", expires_in: 900 })]);
    const t = new HttpTransport({ baseUrl: BASE, fetch: f.fn });
    expect((await err(t.createSession({ username: "u", password: "p" }))).code).toBe(
      "unexpected_session_created",
    );
    expect(t.hasSession).toBe(false);
  });

  it("token expires locally after expires_in without calling the network", async () => {
    let now = 0;
    const { t, calls } = await logged([], () => now);
    now = 899_999;
    expect(t.hasSession).toBe(true);
    now = 900_000;
    expect((await err(t.getSession())).status).toBe(401);
    expect(calls.length).toBe(1);
  });
});

describe("HttpTransport live boundary", () => {
  const walk = (d: string): string[] =>
    readdirSync(d, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? (e.name === "test" ? [] : walk(join(d, e.name))) : [join(d, e.name)],
    );
  const src = join(__dirname, "..");
  const files = walk(src).filter((f) => /\.(ts|tsx)$/.test(f) && !f.endsWith("http-transport.ts"));

  it("only the live runtime imports http-transport", () => {
    for (const f of files.filter(f => !f.endsWith("live-runtime.ts"))) expect(readFileSync(f, "utf8"), f).not.toMatch(/http-transport/);
  });
  it("transport has no storage, logging, global fetch or env access", () => {
    const code = readFileSync(join(src, "data/http-transport.ts"), "utf8").replace(/\/\/.*$/gm, "");
    expect(code).not.toMatch(
      /localStorage|sessionStorage|console\.|globalThis|window\.|import\.meta\.env|process\.env|[^.\w]fetch\(/,
    );
  });
});

