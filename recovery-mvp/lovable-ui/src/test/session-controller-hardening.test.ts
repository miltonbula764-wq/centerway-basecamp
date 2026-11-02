// L03.2-PREP hardening: regression tests for races, draft immutability,
// status guards and local directory checks. Offline: controllable fake transport.
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SessionController } from "@/data/session-controller";
import { L01Error, type L01Transport } from "@/data/transport";
import type { ClientDirectoryPage, OperationRequest, SessionInfo } from "@/domain/l01";
import type { ClientJourney } from "@/domain/f06";

const bundle = JSON.parse(
  readFileSync(join(__dirname, "fixtures/l03-prep-v1/capture.json"), "utf8"),
) as { cases: { id: string; response: { json: unknown } | null }[] };
const journey = (
  bundle.cases.find((c) => c.id === "journey-initial")!.response!.json as { data: ClientJourney }
).data;

const TA = "a1000000-0000-0000-0000-000000000001";
const TB = "b1000000-0000-0000-0000-000000000001";
const CA = "a2000000-0000-0000-0000-000000000001";
const CB = "b2000000-0000-0000-0000-000000000001";

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((r, j) => ((resolve = r), (reject = j)));
  return { promise, resolve, reject };
}

const session: SessionInfo = {
  username: "alice",
  principal: "p-alice",
  clients: { [TA]: [CA], [TB]: [CB] },
  operations: ["intervene", "investigate"],
  company_tenants: [TA],
};
const page = (id: string, name: string): ClientDirectoryPage =>
  ({
    data: [{ client_id: id, display_name: name }],
    next_cursor: null,
    demo: false,
  }) as ClientDirectoryPage;

/** Each listClients/getJourney/operate call returns a pending deferred the test controls. */
class Controlled implements L01Transport {
  readonly mode = "live" as const;
  lists: ReturnType<typeof deferred<ClientDirectoryPage>>[] = [];
  journeys: ReturnType<typeof deferred<ClientJourney>>[] = [];
  ops: { req: OperationRequest; d: ReturnType<typeof deferred<never>> }[] = [];
  async createSession() {
    return { token: "x", expires_in: 900 } as never;
  }
  async getSession() {
    return session;
  }
  async deleteSession() {}
  listClients() {
    const d = deferred<ClientDirectoryPage>();
    this.lists.push(d);
    return d.promise;
  }
  getJourney() {
    const d = deferred<ClientJourney>();
    this.journeys.push(d);
    return d.promise;
  }
  operate(_t: string, _c: string, req: OperationRequest) {
    const d = deferred<never>();
    this.ops.push({ req, d });
    return d.promise;
  }
}
const tick = () => new Promise((r) => setTimeout(r, 0));
const err = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e: L01Error) => e,
  );

async function ready() {
  const t = new Controlled();
  const c = new SessionController(t);
  await c.login("alice", "s3cr3t-pw");
  return { t, c };
}
async function withClient() {
  const r = await ready();
  const p = r.c.selectTenant(TA);
  await tick();
  r.t.lists[0]!.resolve(page(CA, "SYNTHETIC client A"));
  await p;
  const j = r.c.selectClient(CA);
  await tick();
  r.t.journeys[0]!.resolve(journey);
  await j;
  return r;
}

describe("SessionController hardening", () => {
  it("A→B→A tenant switch: late A response cannot overwrite current state", async () => {
    const { t, c } = await ready();
    const a1 = err(c.selectTenant(TA));
    const b = err(c.selectTenant(TB));
    const a2 = c.selectTenant(TA);
    await tick();
    t.lists[2]!.resolve(page(CA, "fresh A"));
    await a2;
    t.lists[1]!.resolve(page(CB, "stale B"));
    t.lists[0]!.resolve(page(CA, "stale A"));
    expect((await a1)?.code).toBe("stale_response");
    expect((await b)?.code).toBe("stale_response");
    expect(c.state.tenant).toBe(TA);
    expect(c.state.directory.map((d) => d.display_name)).toEqual(["fresh A"]);
  });

  it("logout during a pending request: late response does not resurrect state", async () => {
    const { t, c } = await ready();
    const p = err(c.selectTenant(TA));
    await tick();
    await c.logout();
    t.lists[0]!.resolve(page(CA, "late"));
    expect((await p)?.code).toBe("stale_response");
    expect(c.state.status).toBe("logged_out");
    expect(c.state.directory).toEqual([]);
    expect(c.state.tenant).toBeNull();
  });

  it("401 during a request wipes state; a parallel late success is discarded", async () => {
    const { t, c } = await withClient();
    const j1 = err(c.selectClient(CA));
    await tick();
    t.journeys[1]!.reject(new L01Error("http", 401, "unauthorized"));
    expect((await j1)?.status).toBe(401);
    expect(c.state.status).toBe("expired");
    // A stale late error after reset must not change status either.
    const { t: t2, c: c2 } = await withClient();
    const old = err(c2.selectClient(CA));
    await tick();
    await c2.logout();
    t2.journeys[1]!.reject(new L01Error("http", 403, "forbidden"));
    expect((await old)?.code).toBe("stale_response");
    expect(c2.state.status).toBe("logged_out");
  });

  it("client switch: late journey for previous client cannot overwrite", async () => {
    const { t, c } = await withClient();
    const first = err(c.selectClient(CA));
    const second = c.selectClient(CA);
    await tick();
    t.journeys[2]!.resolve(journey);
    await second;
    t.journeys[1]!.resolve({ ...journey, demo: true } as ClientJourney);
    expect((await first)?.code).toBe("stale_response");
    expect(c.state.journey).toBe(journey);
  });

  it("drafts are copied and frozen: caller mutations cannot alter request_id/arguments", async () => {
    const { t, c } = await withClient();
    const req = {
      request_id: "r-1",
      operation: "intervene",
      arguments: { note: "a" },
    } as unknown as OperationRequest;
    const d = c.draft(req);
    (req as { request_id: string }).request_id = "r-hacked";
    (req.arguments as unknown as { note: string }).note = "hacked";
    expect(() => {
      (d.request.arguments as unknown as { note: string }).note = "x";
    }).toThrow();
    const listed = c.listDrafts()[0]!;
    expect(listed).not.toBe(d);
    expect(() => {
      (listed.request as { request_id: string }).request_id = "y";
    }).toThrow();
    const s = c.submit("r-1");
    await tick();
    expect(t.ops[0]!.req.request_id).toBe("r-1");
    expect(t.ops[0]!.req.arguments).toEqual({ note: "a" });
    t.ops[0]!.d.reject(new L01Error("network", null, "connection_refused"));
    await err(s);
    // Explicit resend keeps identical request.
    const again = c.listDrafts()[0]!;
    expect(again.request).toEqual({
      request_id: "r-1",
      operation: "intervene",
      arguments: { note: "a" },
    });
    expect(again.lastError?.kind).toBe("network");
  });

  it("selectClient refuses ids not in the server directory (backend stays sovereign)", async () => {
    const { t, c } = await ready();
    const p = c.selectTenant(TA);
    await tick();
    t.lists[0]!.resolve(page(CA, "A"));
    await p;
    expect((await err(c.selectClient(CB)))?.code).toBe("client_not_in_directory");
    expect(t.journeys.length).toBe(0);
  });

  it("guards: authenticating blocks everything; forbidden allows reads but not drafts/submit", async () => {
    const t = new Controlled();
    const c = new SessionController(t);
    const slow = deferred<SessionInfo>();
    t.getSession = () => slow.promise;
    const l = c.login("alice", "s3cr3t-pw");
    await tick();
    expect(c.state.status).toBe("authenticating");
    expect((await err(c.selectTenant(TA)))?.code).toBe("session_not_ready");
    slow.resolve(session);
    await l;

    const r = await withClient();
    const j = err(r.c.selectClient(CA));
    await tick();
    r.t.journeys[1]!.reject(new L01Error("http", 403, "forbidden"));
    await j;
    expect(r.c.state.status).toBe("forbidden");
    const zreq = {
      request_id: "z",
      operation: "intervene",
      arguments: {},
    } as unknown as OperationRequest;
    let code: string | null = null;
    try {
      r.c.draft(zreq);
    } catch (e) {
      code = (e as L01Error).code;
    }
    expect(code).toBe("session_forbidden");
    expect((await err(r.c.submit("z")))?.code).toBe("session_forbidden");
    // A successful read re-establishes authenticated (server granted it).
    const ok = r.c.selectClient(CA);
    await tick();
    r.t.journeys[2]!.resolve(journey);
    await ok;
    expect(r.c.state.status).toBe("authenticated");
  });

  it("unavailable without session blocks navigation; no silent re-authentication", async () => {
    const t = new Controlled();
    t.createSession = async () => {
      throw new L01Error("network", null, "connection_refused");
    };
    const c = new SessionController(t);
    await err(c.login("alice", "s3cr3t-pw"));
    expect(c.state.status).toBe("unavailable");
    expect((await err(c.selectTenant(TA)))?.code).toBe("session_not_ready");
  });

  it("state and errors never carry credentials; company and client tenants stay distinct", async () => {
    const { c } = await withClient();
    const dump = JSON.stringify(c.state);
    expect(dump).not.toMatch(/s3cr3t-pw|Bearer|"token"|password/i);
    expect(c.state.companyTenants).toEqual([TA]);
    expect(c.state.clientTenants).toEqual([TA, TB].sort());
  });
});

