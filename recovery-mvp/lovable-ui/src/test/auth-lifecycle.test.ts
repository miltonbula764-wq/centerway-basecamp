// Auth lifecycle regressions: stale login/logout/401 responses must never
// authenticate, clear or replace a newer session. Deterministic: controlled promises.
import { describe, expect, it } from "vitest";
import { SessionController } from "@/data/session-controller";
import { HttpTransport } from "@/data/http-transport";
import { L01Error, type L01Transport } from "@/data/transport";
import type { SessionCreated, SessionInfo } from "@/domain/l01";

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((r, j) => ((resolve = r), (reject = j)));
  return { promise, resolve, reject };
}
const tick = () => new Promise((r) => setTimeout(r, 0));
const err = (p: Promise<unknown>) =>
  p.then(
    () => null,
    (e: L01Error) => e,
  );

const T = "a1000000-0000-0000-0000-000000000001";
const info = (u: string): SessionInfo => ({
  username: u,
  principal: `p-${u}`,
  clients: { [T]: [] },
  operations: [],
  company_tenants: [],
});
const created = (ttl = 900) =>
  ({ token_type: "Bearer", access_token: "x", expires_in: ttl }) as SessionCreated;

class Ctl implements L01Transport {
  readonly mode = "live" as const;
  creates: ReturnType<typeof deferred<SessionCreated>>[] = [];
  gets: ReturnType<typeof deferred<SessionInfo>>[] = [];
  deletes: ReturnType<typeof deferred<void>>[] = [];
  createSession() {
    const d = deferred<SessionCreated>();
    this.creates.push(d);
    return d.promise;
  }
  getSession() {
    const d = deferred<SessionInfo>();
    this.gets.push(d);
    return d.promise;
  }
  deleteSession() {
    const d = deferred<void>();
    this.deletes.push(d);
    return d.promise;
  }
  listClients(): never {
    throw new Error("unused");
  }
  getJourney(): never {
    throw new Error("unused");
  }
  operate(): never {
    throw new Error("unused");
  }
}

async function loggedIn(t: Ctl, c: SessionController, u = "alice") {
  const p = c.login(u, "pw");
  await tick();
  t.creates.at(-1)!.resolve(created());
  await tick();
  t.gets.at(-1)!.resolve(info(u));
  await p;
}

describe("SessionController auth lifecycle", () => {
  it("logout during pending createSession: late success never authenticates", async () => {
    const t = new Ctl();
    const c = new SessionController(t);
    const p = err(c.login("alice", "pw"));
    await tick();
    const lo = c.logout();
    expect(c.state.status).toBe("logged_out");
    t.creates[0]!.resolve(created());
    t.deletes[0]?.resolve();
    await lo;
    expect((await p)?.code).toBe("stale_response");
    expect(t.gets.length).toBe(0);
    expect(c.state.status).toBe("logged_out");
    expect(c.state.session).toBeNull();
  });

  it("logout during pending getSession: late session never authenticates", async () => {
    const t = new Ctl();
    const c = new SessionController(t);
    const p = err(c.login("alice", "pw"));
    await tick();
    t.creates[0]!.resolve(created());
    await tick();
    const lo = c.logout();
    t.gets[0]!.resolve(info("alice"));
    t.deletes[0]!.resolve();
    await lo;
    expect((await p)?.code).toBe("stale_response");
    expect(c.state.status).toBe("logged_out");
    expect(c.state.session).toBeNull();
  });

  it("two logins resolving in reverse order: the last request wins", async () => {
    const t = new Ctl();
    const c = new SessionController(t);
    const a = err(c.login("alice", "pw"));
    const b = c.login("bob", "pw");
    await tick();
    t.creates[1]!.resolve(created());
    await tick();
    t.gets[0]!.resolve(info("bob"));
    await b;
    t.creates[0]!.resolve(created());
    expect((await a)?.code).toBe("stale_response");
    expect(t.gets.length).toBe(1);
    expect(c.state.session?.username).toBe("bob");
    expect(c.state.status).toBe("authenticated");
  });

  it("late failure / 401 of an old login does not touch the newer session", async () => {
    const t = new Ctl();
    const c = new SessionController(t);
    const a = err(c.login("alice", "pw"));
    await tick();
    await loggedIn(t, c, "bob");
    t.creates[0]!.reject(new L01Error("http", 401, "unauthorized"));
    expect((await a)?.code).toBe("stale_response");
    expect(c.state.status).toBe("authenticated");
    expect(c.state.session?.username).toBe("bob");
    expect(c.state.lastError).toBeNull();
  });

  it("logout wipes state immediately; a late logout cannot clear a newer login", async () => {
    const t = new Ctl();
    const c = new SessionController(t);
    await loggedIn(t, c, "alice");
    const lo = c.logout();
    expect(c.state.status).toBe("logged_out");
    expect(c.state.session).toBeNull();
    await loggedIn(t, c, "bob");
    t.deletes[0]!.resolve();
    await lo;
    expect(c.state.status).toBe("authenticated");
    expect(c.state.session?.username).toBe("bob");
  });

  it("TTL counts from session creation, not from the end of getSession", async () => {
    const t = new Ctl();
    let now = 0;
    const c = new SessionController(t, () => now);
    const p = c.login("alice", "pw");
    await tick();
    t.creates[0]!.resolve(created(900));
    await tick();
    now = 100_000;
    t.gets[0]!.resolve(info("alice"));
    await p;
    now = 899_999;
    expect(c.state.status).toBe("authenticated");
    now = 900_000;
    expect(c.state.status).toBe("expired");
  });
});

/* ---------- HttpTransport credential generations (simulated fetch) ---------- */

const json = (status: number, body: unknown) =>
  new Response(body === null ? null : JSON.stringify(body), { status });
const okSession = (tok: string) =>
  json(201, { token_type: "Bearer", access_token: tok, expires_in: 900 });
const sessionBody = { data: undefined, ...info("alice") };

function http() {
  const calls: { url: string; init: RequestInit; d: ReturnType<typeof deferred<Response>> }[] = [];
  const t = new HttpTransport({
    baseUrl: "https://api.example",
    fetch: (url, init) => {
      const d = deferred<Response>();
      calls.push({ url, init, d });
      return d.promise;
    },
  });
  const auth = (i: number) => (calls[i]!.init.headers as Record<string, string>)["Authorization"];
  return { t, calls, auth };
}

describe("HttpTransport auth lifecycle", () => {
  it("older createSession resolving last never installs its token", async () => {
    const { t, calls, auth } = http();
    const a = err(t.createSession({ username: "a", password: "p" }));
    const b = t.createSession({ username: "b", password: "p" });
    calls[1]!.d.resolve(okSession("tok-B"));
    await b;
    calls[0]!.d.resolve(okSession("tok-A"));
    expect((await a)?.code).toBe("stale_response");
    void t.getSession().catch(() => {});
    await tick();
    expect(auth(2)).toBe("Bearer tok-B");
  });

  it("late 401 for an old token does not clear the newer token", async () => {
    const { t, calls, auth } = http();
    const l1 = t.createSession({ username: "a", password: "p" });
    calls[0]!.d.resolve(okSession("tok-A"));
    await l1;
    const old = err(t.getSession());
    await tick();
    const l2 = t.createSession({ username: "b", password: "p" });
    calls[2]!.d.resolve(okSession("tok-B"));
    await l2;
    calls[1]!.d.resolve(json(401, { error: { code: "unauthorized" } }));
    expect((await old)?.status).toBe(401);
    expect(t.hasSession).toBe(true);
    const g = t.getSession();
    await tick();
    expect(auth(3)).toBe("Bearer tok-B");
    calls[3]!.d.resolve(json(200, sessionBody));
    await g;
  });

  it("logout clears immediately, revokes with the captured token, and cannot clear a newer login", async () => {
    const { t, calls, auth } = http();
    const l1 = t.createSession({ username: "a", password: "p" });
    calls[0]!.d.resolve(okSession("tok-A"));
    await l1;
    const lo = t.deleteSession();
    expect(t.hasSession).toBe(false);
    await tick();
    expect(calls[1]!.init.method).toBe("DELETE");
    expect(auth(1)).toBe("Bearer tok-A");
    const l2 = t.createSession({ username: "b", password: "p" });
    calls[2]!.d.resolve(okSession("tok-B"));
    await l2;
    calls[1]!.d.resolve(new Response(null, { status: 204 }));
    await lo;
    expect(t.hasSession).toBe(true);
  });

  it("logout during pending createSession: late token is never installed", async () => {
    const { t, calls } = http();
    const l = err(t.createSession({ username: "a", password: "p" }));
    await t.deleteSession();
    calls[0]!.d.resolve(okSession("tok-A"));
    expect((await l)?.code).toBe("stale_response");
    expect(t.hasSession).toBe(false);
    expect(calls.length).toBe(1);
  });

  it("current login with invalid credentials keeps HTTP 401 and its code (not stale)", async () => {
    const { t, calls } = http();
    const l = err(t.createSession({ username: "a", password: "bad" }));
    calls[0]!.d.resolve(json(401, { error: { code: "invalid_credentials" } }));
    const e = await l;
    expect(e?.kind).toBe("http");
    expect(e?.status).toBe(401);
    expect(e?.code).toBe("invalid_credentials");
    expect(t.hasSession).toBe(false);
  });
});

