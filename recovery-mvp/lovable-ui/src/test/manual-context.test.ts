import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import { HttpTransport } from "@/data/http-transport";
import { LiveRuntime } from "@/data/live-runtime";
import { L01Error, type L01Transport } from "@/data/transport";
import type { ClientJourney, ManualContext } from "@/domain/f06";
const T = "a1000000-0000-0000-0000-000000000001",
  C = "a2000000-0000-0000-0000-000000000001",
  B = "b1000000-0000-0000-0000-000000000001";
const context = {
  version: "t02-v1",
  tenant_id: T,
  client_id: C,
  principal: "p",
  limit_per_collection: 100,
  truncated: {
    factors: false,
    evidence: false,
    verifications: false,
    catalog: false,
    policies: false,
    revocations: false,
    resources: false,
    audit: false,
  },
  factors: [],
  evidence: [],
  verifications: [],
  catalog: [],
  policies: [],
  revocations: [],
  resources: [],
  audit: [],
} as ManualContext;
const journey = JSON.parse(
  readFileSync(__dirname + "/fixtures/l03-prep-v1/capture.json", "utf8"),
).cases.find((c: { id: string }) => c.id === "journey-initial").response.json.data as ClientJourney;
async function runtime() {
  const t: L01Transport = {
    mode: "live",
    createSession: async () => ({
      access_token: "secret-memory-only",
      token_type: "Bearer",
      expires_in: 900,
      demo: false,
    }),
    getSession: async () => ({
      username: "u",
      principal: "p",
      clients: { [T]: [C] },
      operations: [],
      company_tenants: [],
    }),
    deleteSession: async () => {},
    listClients: async () => ({
      data: [{ client_id: C, display_name: "From API" }],
      next_cursor: null,
      demo: false,
    }),
    getJourney: async () => ({ ...journey, tenant_id: T, client_id: C }),
    getManualContext: async () => structuredClone(context),
    operate: vi.fn(),
  };
  const r = new LiveRuntime(t);
  await r.login("u", "p");
  return { r, t };
}
function deferred<T>() {
  let resolve!: (v: T) => void;
  return {
    promise: new Promise<T>((r) => {
      resolve = r;
    }),
    resolve,
  };
}
describe("manual context read contract and session boundary", () => {
  it("uses actual endpoint path and Authorization without writing", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: "secret-memory-only",
            token_type: "Bearer",
            expires_in: 900,
            demo: false,
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ data: context, demo: false }), { status: 200 }),
      );
    const t = new HttpTransport({ baseUrl: "https://api.example", fetch });
    await t.createSession({ username: "u", password: "test" });
    expect(await t.getManualContext(T, C)).toEqual(context);
    expect(fetch.mock.calls[1]![0]).toBe(
      `https://api.example/v1/tenants/${T}/clients/${C}/manual-context`,
    );
    expect(fetch.mock.calls[1]![1].method).toBe("GET");
  });
  it.each(["tenant", "client", "rows", "limit", "version", "audit", "policy"])(
    "rejects malformed or foreign %s data",
    async (kind) => {
      const value = structuredClone(context);
      if (kind === "tenant") value.tenant_id = B;
      if (kind === "client") value.client_id = B;
      if (kind === "rows") value.factors = [{ tenant_id: B, client_id: C }];
      if (kind === "audit") value.audit = [{ tenant_id: T, snapshot: { client_id: B } }];
      if (kind === "policy") value.policies = [{ tenant_id: T, client_id: C, principal: "other" }];
      if (kind === "limit") Object.assign(value, { limit_per_collection: 500 });
      if (kind === "version") Object.assign(value, { version: "unknown" });
      const fetch = vi
        .fn()
        .mockResolvedValueOnce(
          new Response(
            JSON.stringify({
              access_token: "secret-memory-only",
              token_type: "Bearer",
              expires_in: 900,
              demo: false,
            }),
            { status: 201 },
          ),
        )
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ data: value, demo: false }), { status: 200 }),
        );
      const t = new HttpTransport({ baseUrl: "https://api.example", fetch });
      await t.createSession({ username: "u", password: "test" });
      await expect(t.getManualContext(T, C)).rejects.toMatchObject({
        code: "unexpected_manual_context",
      });
    },
  );
  it("discards a late context after logout without repopulating the displayed cache", async () => {
    const { r, t } = await runtime();
    const pending = deferred<ManualContext>();
    const started = deferred<void>();
    t.getManualContext = () => {
      started.resolve();
      return pending.promise;
    };
    const work = r.loadManual(C).catch((e) => e);
    await started.promise;
    await r.logout();
    pending.resolve(context);
    await work;
    expect(r.getSnapshot().customers).toEqual([]);
    expect(r.getSnapshot().auth.session).toBeNull();
  });
  it("server expiry during context read clears the session and view", async () => {
    const { r, t } = await runtime();
    t.getManualContext = async () => {
      throw new L01Error("http", 401, "expired");
    };
    await expect(r.loadManual(C)).rejects.toMatchObject({ status: 401 });
    expect(r.getSnapshot().auth.session).toBeNull();
    expect(r.getSnapshot().customers).toEqual([]);
  });
});
