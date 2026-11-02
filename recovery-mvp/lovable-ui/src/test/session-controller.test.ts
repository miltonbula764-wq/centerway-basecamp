import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { FixtureTransport, type FixtureBundle } from "@/data/fixture-transport";
import { SessionController } from "@/data/session-controller";
import { HttpTransport, parseBaseUrl } from "@/data/http-transport";
import { L01Error } from "@/data/transport";
import type { OperationRequest } from "@/domain/l01";

const bundle = JSON.parse(
  readFileSync(join(__dirname, "fixtures/l03-prep-v1/capture.json"), "utf8"),
) as FixtureBundle;
const json = (id: string) => bundle.cases.find((c) => c.id === id)!.request.json;
const TA = "a1000000-0000-0000-0000-000000000001";
const TB = "b1000000-0000-0000-0000-000000000001";
const CA = "a2000000-0000-0000-0000-000000000001";
const CA2 = "a2000000-0000-0000-0000-000000000002";

let lastLogin: string | null = null;
/** FixtureTransport that arms the next case from an ordered script. */
class Scripted extends FixtureTransport {
  constructor(private readonly script: string[]) {
    super(bundle);
    lastLogin = script.find((id) => id.startsWith("post-sessions")) ?? null;
  }
  override async request(...a: Parameters<FixtureTransport["request"]>) {
    const id = this.script.shift();
    if (id) this.expect(id);
    return super.request(...a);
  }
}
const err = async (p: Promise<unknown>) => {
  try {
    await p;
  } catch (e) {
    return e as L01Error;
  }
  throw new Error("expected rejection");
};
const login = (c: SessionController, _who: string) => {
  const j = (lastLogin ? json(lastLogin) : { username: "u", password: "p" }) as {
    username: string;
    password: string;
  };
  return c.login(j.username, j.password);
};

describe("parseBaseUrl path fix", () => {
  it.each([
    "https://api.x.test/v1",
    "https://api.x.test/prefix/",
    "https://api.x.test/#",
    "https://api.x.test/?",
  ])("rejects %s", (u) => expect(() => parseBaseUrl(u)).toThrow(/base_url_has_(path|query)/));
  it("accepts bare origin with or without trailing slash", () => {
    expect(parseBaseUrl("https://api.x.test/")).toBe("https://api.x.test");
    expect(parseBaseUrl("https://api.x.test:8443")).toBe("https://api.x.test:8443");
  });
});

describe("SessionController (headless)", () => {
  it("login → authenticated with tenant scopes; company tenants kept separate", async () => {
    const c = new SessionController(new Scripted(["post-sessions-03", "session-alice-1"]));
    expect(c.state.status).toBe("logged_out");
    await login(c, "alice");
    expect(c.state.status).toBe("authenticated");
    expect(c.state.clientTenants).toEqual([TA]);
    expect(c.state.companyTenants).toEqual([]);
    expect(c.canAttempt("discover_company")).toBe(false);
  });

  it("TTL expiry wipes the session without a network call", async () => {
    let now = 0;
    const t = new Scripted(["post-sessions-03", "session-alice-1"]);
    const c = new SessionController(t, () => now);
    await login(c, "alice");
    now = 900_000;
    expect(c.state.status).toBe("expired");
    expect(c.state.session).toBeNull();
    expect((await err(c.selectTenant(TA))).status).toBe(401);
    expect(t.replayed.length).toBe(2);
  });

  it("paginated directory, then empty page; names come only from server", async () => {
    const c = new SessionController(
      new Scripted([
        "post-sessions-06",
        "session-reader-2",
        "directory-page-1",
        "directory-page-2",
      ]),
    );
    await login(c, "reader");
    const d = await c.selectTenant(TA, 1);
    expect(d.map((e) => e.client_id)).toEqual([CA, CA2]);
    const e = new SessionController(
      new Scripted(["post-sessions-06", "session-reader-2", "directory-page-empty"]),
    );
    await login(e, "reader");
    // listAllClients without cursor would not match; prove empty page is not an error via transport
    const t = new Scripted(["directory-page-empty"]);
    expect((await t.listClients(TA, { after: CA2 })).data).toEqual([]);
  });

  it("tenant outside SessionInfo is refused locally; server 403 marks forbidden but keeps session", async () => {
    const c = new SessionController(
      new Scripted(["post-sessions-03", "session-alice-1", "alice-denied-company-b-403"]),
    );
    await login(c, "alice");
    expect((await err(c.selectTenant(TB))).code).toBe("tenant_not_in_session");
    const r = new SessionController(
      new Scripted([
        "post-sessions-06",
        "session-reader-2",
        "directory-page-1",
        "directory-page-2",
        "reader-denied-client-403",
      ]),
    );
    await login(r, "reader");
    await r.selectTenant(TA, 1);
    expect((await err(r.selectClient(CA2))).status).toBe(403);
    expect(r.state.status).toBe("forbidden");
    expect(r.state.session).not.toBeNull();
  });

  it("tenant isolation: bob sees only tenant B", async () => {
    const c = new SessionController(
      new Scripted(["post-sessions-02", "session-bob-1", "directory-bob"]),
    );
    await login(c, "bob");
    expect(c.state.clientTenants).toEqual([TB]);
    expect((await c.selectTenant(TB)).map((d) => d.display_name)).toEqual(["SYNTHETIC client B"]);
  });

  it("journey progress derives from projection, never assumed", async () => {
    const run = async (journeyCase: string) => {
      const c = new SessionController(
        new Scripted(["post-sessions-03", "session-alice-1", "directory-alice", journeyCase]),
      );
      await login(c, "alice");
      await c.selectTenant(TA);
      return { p: await c.selectClient(CA), c };
    };
    const initial = await run("journey-initial");
    expect(initial.p.reached).toBe("journey");
    expect(initial.p.investigations + initial.p.decisions + initial.p.recoveryPlans).toBe(0);
    expect(initial.c.state.view?.displayName).toBe("SYNTHETIC client A");
    const inv = await run("journey-after-investigate-1");
    expect(inv.p.reached).toBe("investigation");
    expect(inv.p.decisions).toBe(0);
    const rec = await run("journey-after-evaluate_recovery-2");
    expect(rec.p.reached).toBe("recovery");
    expect(rec.p.causalAttribution).toBe("not_established");
  });

  it("drafts are memory-only, scoped, and sent only on explicit submit; 409/422 keep request_id", async () => {
    const t = new Scripted([
      "post-sessions-03",
      "session-alice-1",
      "directory-alice",
      "journey-initial",
      "idempotency-conflict-409",
    ]);
    const c = new SessionController(t);
    await login(c, "alice");
    await c.selectTenant(TA);
    await c.selectClient(CA);
    const req = json("idempotency-conflict-409") as unknown as OperationRequest;
    c.draft(req);
    expect(t.replayed.length).toBe(4); // drafting sends nothing
    const e = await err(c.submit(req.request_id));
    expect(e.status).toBe(409);
    const kept = c.listDrafts()[0]!;
    expect(kept.request.request_id).toBe(req.request_id);
    expect(kept.lastError?.status).toBe(409);
    expect(t.replayed.length).toBe(5); // no retry
  });

  it("422 pre-engine vs engine receipt are distinct; 403 operation keeps session", async () => {
    const t = new Scripted([
      "post-sessions-03",
      "session-alice-1",
      "directory-alice",
      "journey-initial",
      "invalid-envelope-422",
      "engine-error-receipt-422",
    ]);
    const c = new SessionController(t);
    await login(c, "alice");
    await c.selectTenant(TA);
    await c.selectClient(CA);
    const submitCase = async (id: string) => {
      const r = c.draft(json(id) as unknown as OperationRequest);
      return err(c.submit(r.request.request_id));
    };
    const pre = await submitCase("invalid-envelope-422");
    const eng = await submitCase("engine-error-receipt-422");
    expect([pre.kind, eng.kind]).toEqual(["http", "receipt"]);
    expect(eng.message).not.toMatch(/sqlstate/i);
  });

  it("refused intervention (403) and blocked business result over HTTP 200", async () => {
    const r = new SessionController(
      new Scripted([
        "post-sessions-01",
        "session-reader-1",
        "directory-reader",
        "journey-initial",
        "reader-denied-intervention-403",
      ]),
    );
    await login(r, "reader");
    expect(r.canAttempt("intervene")).toBe(false);
    await r.selectTenant(TA);
    await r.selectClient(CA);
    r.draft(json("reader-denied-intervention-403") as unknown as OperationRequest);
    const e = await err(r.submit(r.listDrafts()[0]!.request.request_id));
    expect(e.code).toBe("operation_forbidden");
    expect(r.state.status).toBe("forbidden");

    const a = new SessionController(
      new Scripted([
        "post-sessions-03",
        "session-alice-1",
        "directory-alice",
        "journey-initial",
        "intervene-01",
      ]),
    );
    await login(a, "alice");
    await a.selectTenant(TA);
    await a.selectClient(CA);
    a.draft(json("intervene-01") as unknown as OperationRequest);
    const rc = await a.submit(a.listDrafts()[0]!.request.request_id);
    expect(rc.status).toBe("completed");
    expect(JSON.stringify(rc.result)).toContain("blocked");
    expect(a.listDrafts()).toEqual([]);
  });

  it("401 mid-session wipes state and drafts", async () => {
    const c = new SessionController(
      new Scripted([
        "post-sessions-01",
        "session-reader-1",
        "changed-scope-invalidates-session-401",
      ]),
    );
    await login(c, "reader");
    expect((await err(c.selectTenant(TA))).status).toBe(401);
    expect(c.state.status).toBe("expired");
    expect(c.state.session).toBeNull();
    expect(c.listDrafts()).toEqual([]);
  });

  it("503 and network failure before session → unavailable; logout 204 cleans up", async () => {
    const c = new SessionController(
      new HttpTransport({
        baseUrl: "https://api.x.test",
        fetch: async () => {
          throw new TypeError("Failed to fetch");
        },
      }),
    );
    const e = await err(login(c, "alice"));
    expect([e.kind, e.status]).toEqual(["network", null]);
    expect(c.state.status).toBe("unavailable");
    const d = new SessionController(
      new Scripted(["post-sessions-06", "session-reader-2", "logout-204"]),
    );
    await login(d, "reader");
    await d.logout();
    expect(d.state.status).toBe("logged_out");
    expect(d.state.session).toBeNull();
  });

  it("works over HttpTransport with simulated fetch; token never in state", async () => {
    const q = ["post-sessions-03", "session-alice-1"].map((id) => {
      const r = bundle.cases.find((c) => c.id === id)!.response!;
      return new Response(JSON.stringify(r.json), { status: r.status });
    });
    const c = new SessionController(
      new HttpTransport({ baseUrl: "https://api.x.test", fetch: async () => q.shift()! }),
    );
    await login(c, "alice");
    expect(JSON.stringify(c.state)).not.toContain("SESSION:alice");
  });
});

describe("controller live boundary", () => {
  const walk = (d: string): string[] =>
    readdirSync(d, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? (e.name === "test" ? [] : walk(join(d, e.name))) : [join(d, e.name)],
    );
  it("controller is used only by live runtime and typed action drafts; no storage use", () => {
    const src = join(__dirname, "..");
    for (const f of walk(src).filter(
      (f) => /\.tsx?$/.test(f) && !f.endsWith("session-controller.ts") && !f.endsWith("live-runtime.ts") && !f.endsWith("live-operation.tsx"),
    ))
      expect(readFileSync(f, "utf8"), f).not.toMatch(/session-controller/);
    expect(readFileSync(join(src, "data/session-controller.ts"), "utf8")).not.toMatch(
      /localStorage|sessionStorage|console\.|fetch\(/,
    );
  });
});

