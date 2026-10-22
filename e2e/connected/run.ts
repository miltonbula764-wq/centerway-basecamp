/** Real disposable GoTrue/PostgreSQL/C01. ONLY PostHog is a controlled OAuth mock. */
import assert from "node:assert/strict";
import { randomBytes, randomUUID } from "node:crypto";
import postgres from "postgres";
import { ingestionHandler } from "../../supabase/functions/_shared/ingestion-handler";
import { Connector, handler } from "../../src/server/connected/service";
import {
  challenge,
  config,
  digest,
  seal,
  unseal,
  scopes,
} from "../../src/server/connected/security";

if (
  process.env.CW_LOCAL_MVP !== "1" &&
  !(process.env.GITHUB_ACTIONS === "true" && process.env.RUNNER_ENVIRONMENT === "github-hosted")
)
  throw Error("Disposable environment required");
const pub = await Bun.file("e2e/private/public.json").json();
assert.equal(pub.url, "http://127.0.0.1:54321");
const sql = postgres("postgres://postgres@127.0.0.1:5432/cw_e2e", { max: 3, onnotice: () => {} });
let assertions = 0;
const eq = (a: unknown, b: unknown) => {
  assert.deepEqual(a, b);
  assertions++;
};
const ok = (a: unknown) => {
  assert.ok(a);
  assertions++;
};
const run = randomUUID().slice(0, 8);
const password = "SyntheticOnly-20.8-" + randomUUID();
async function auth(email: string) {
  const r = await fetch(pub.url + "/auth/v1/signup", {
    method: "POST",
    headers: { apikey: pub.anon, "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  assert.equal(r.status, 200);
  const u = await r.json();
  const p = await fetch(pub.url + "/auth/v1/token?grant_type=password", {
    method: "POST",
    headers: { apikey: pub.anon, "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  assert.equal(p.status, 200);
  return await p.json();
}
async function rest(user: any, path: string, body?: unknown, method = body ? "POST" : "GET") {
  const r = await fetch(pub.url + "/rest/v1/" + path, {
    method,
    headers: {
      apikey: pub.anon,
      authorization: "Bearer " + user.access_token,
      "content-type": "application/json",
      prefer: "return=representation",
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const value = await r.json();
  if (!r.ok) throw Error("fixture REST failed: " + r.status + " " + JSON.stringify(value));
  return value;
}
const a = await auth(`connected-a-${run}@example.test`),
  b = await auth(`connected-b-${run}@example.test`),
  operator = await auth(`connected-op-${run}@example.test`);
const tenantA = await rest(a, "rpc/create_tenant", {
    _name: "Connected A " + run,
    _subject_unit_type: "organization",
  }),
  tenantB = await rest(b, "rpc/create_tenant", {
    _name: "Connected B " + run,
    _subject_unit_type: "organization",
  });
await rest(a, "rpc/add_tenant_member", {
  _tenant_id: tenantA,
  _user_id: operator.user.id,
  _role: "operator",
});
await sql`DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='cw_connected_test') THEN CREATE ROLE cw_connected_test LOGIN NOINHERIT; END IF; END $$`;
await sql`GRANT centerway_connector_backend TO cw_connected_test`;
const mockOrigin = "http://127.0.0.1:54560",
  origin = "http://127.0.0.1:54561";
Object.assign(process.env, {
  CW_LOCAL_MVP: "1",
  CW_CONNECTOR_ORIGIN: origin,
  CW_POSTHOG_CLIENT_ID: origin + "/api/connected/metadata",
  CW_CONNECTOR_DATABASE_URL: "postgres://cw_connected_test@127.0.0.1:5432/cw_e2e",
  CW_CONNECTOR_KEY: randomBytes(32).toString("base64"),
  CW_POSTHOG_MOCK: mockOrigin,
  SUPABASE_URL: pub.url,
  SUPABASE_PUBLISHABLE_KEY: pub.anon,
  CW_C01_URL: "https://127.0.0.1:54443/functions/v1/ingest-v1/observations",
});
const cfg = config(),
  connector = new Connector(cfg);
let project = 41,
  broad = false,
  badIssuer = false,
  badPage = false,
  rate = false,
  refreshFail = false,
  queryFail = false,
  late = false,
  delay = false,
  refreshes = 0,
  revocations = 0,
  providerCalls = 0;
const codes = new Map<string, any>(),
  tokens = new Map<string, number>(),
  refreshTokens = new Map<string, number>(),
  clients = new Map<string, string>();
const json = (v: unknown, status = 200) => Response.json(v, { status });
const mock = Bun.serve({
  hostname: "127.0.0.1",
  port: 54560,
  async fetch(req) {
    providerCalls++;
    const u = new URL(req.url),
      path = u.pathname;
    if (path === "/.well-known/oauth-authorization-server")
      return json({
        issuer: badIssuer ? "https://evil.invalid" : mockOrigin,
        authorization_endpoint: mockOrigin + "/oauth/authorize/",
        token_endpoint: mockOrigin + "/oauth/token/",
        revocation_endpoint: mockOrigin + "/oauth/revoke/",
        response_types_supported: ["code"], scopes_supported:scopes,token_endpoint_auth_methods_supported:["none"],
        code_challenge_methods_supported: ["S256"],
      });
    if(path==='/.well-known/oauth-protected-resource')return json({resource:mockOrigin,authorization_servers:[mockOrigin],scopes_supported:scopes,bearer_methods_supported:['header']});
    if (path === "/oauth/authorize/") {
      eq(u.searchParams.get("required_access_level"), "project");
      eq(u.searchParams.get("code_challenge_method"), "S256");
      eq(u.searchParams.get("scope"), scopes.join(" "));
      ok(
        [cfg.redirect, "http://127.0.0.1:5173/posthog/callback"].includes(
          u.searchParams.get("redirect_uri")!,
        ),
      );
      const client = u.searchParams.get("client_id")!;
      ok([cfg.clientId, "http://127.0.0.1:5173/api/connected/metadata"].includes(client));
      const metadata = await (await fetch(client)).json();
      eq(metadata.client_id, client);
      eq(metadata["com.posthog"].scopes.slice().sort(), scopes);
      eq(metadata["com.posthog"].optional_scopes, []);
      const code = randomUUID();
      codes.set(code, {
        challenge: u.searchParams.get("code_challenge"),
        project,
        redirect: u.searchParams.get("redirect_uri"),
        client: u.searchParams.get("client_id"),
      });
      const target = new URL(u.searchParams.get("redirect_uri")!);
      target.searchParams.set("code", code);
      target.searchParams.set("state", u.searchParams.get("state")!);
      return Response.redirect(target, 302);
    }
    if (path === "/oauth/token/") {
      const body = new URLSearchParams(await req.text());
      ok(
        [cfg.clientId, "http://127.0.0.1:5173/api/connected/metadata"].includes(
          body.get("client_id")!,
        ),
      );
      let p: number;
      if (body.get("grant_type") === "refresh_token") {
        refreshes++;
        if (refreshFail) return json({ error: "invalid_grant" }, 400);
        p = refreshTokens.get(body.get("refresh_token")!)!;
        refreshTokens.delete(body.get("refresh_token")!);
      } else {
        const c = codes.get(body.get("code")!);
        if (!c) return json({ error: "invalid_grant" }, 400);
        codes.delete(body.get("code")!);
        eq(challenge(body.get("code_verifier")!), c.challenge);
        eq(body.get("redirect_uri"), c.redirect);
        p = c.project;
      }
      if (!p) return json({ error: "invalid_grant" }, 400);
      const access = randomUUID(),
        refresh = randomUUID();
      tokens.set(access, p);
      refreshTokens.set(refresh, p);
      clients.set(access, body.get("client_id")!);
      return json({
        access_token: access,
        refresh_token: refresh,
        token_type: "Bearer",
        scope: scopes.join(" "),
        expires_in: 3600,
        scoped_teams: broad ? [p, 99] : [p],
        scoped_organizations: [],
      });
    }
    if (path === "/oauth/introspect/") {
      const p = tokens.get(req.headers.get("authorization")?.slice(7) || "");
      return json({
        active: !!p,
        is_impersonated: false,
        client_id: clients.get(req.headers.get("authorization")?.slice(7) || ""),
        scope: scopes.join(" "),
        scoped_teams: broad ? [p, 99] : [p],
        scoped_organizations: [],
        exp: Math.floor(Date.now() / 1000) + 3600,
      });
    }
    if (path === "/oauth/revoke/") {
      revocations++;
      return new Response(null, { status: 200 });
    }
    const p = tokens.get(req.headers.get("authorization")?.slice(7) || "");
    if (!p || !path.startsWith(`/api/projects/${p}/`)) return json({ error: "denied" }, 403);
    if (rate) return new Response("{}", { status: 429, headers: { "retry-after": "2" } });
    if (path.endsWith("/groups_types/"))
      return json([{ group_type_index: 0, group_type: "company" }]);
    if (path.endsWith("/groups/")) {
      if (badPage) return json({ results: [], next: "https://evil.invalid/steal" });
      if (!u.searchParams.get("cursor"))
        return json({
          results: [
            {
              group_key: "stable-acme",
              group_properties: { name: "Acme synthetic", email: "never-persist@example.test" },
            },
          ],
          next: `${mockOrigin}/api/projects/${p}/groups/?group_type_index=0&cursor=page2`,
        });
      return json({
        results: [{ group_key: "stable-beta", group_properties: { name: "Beta synthetic" } }],
        next: null,
      });
    }
    if (path.endsWith("/query/")) {
      if (delay) await new Promise((r) => setTimeout(r, 150));
      if (queryFail) return json({ error: "temporary" }, 503);
      const q = await req.json();
      ok(q.query.query.includes("JSONExtractString(properties, '$groups', 'company')"));
      ok(!q.query.query.includes("distinct_id"));
      return json({
        results: [
          ["stable-acme", "workflow_completed", late ? 13 : 10],
          ["stable-beta", "workflow_completed", 5],
          ["unselected", "other_event", 9],
        ],
      });
    }
    if (path === `/api/projects/${p}/`)
      return json({
        id: p,
        name: "Synthetic project " + p,
        live_events_token: "must-never-persist",
      });
    return json({}, 404);
  },
});
const app = Bun.serve({ hostname: "127.0.0.1", port: 54561, fetch: handler });
let c01Failure = 0,
  c01Requests = 0;
const envelopes: any[] = [];
const ingest = ingestionHandler({ url: pub.url, anonKey: pub.anon });
const c01 = Bun.serve({
  hostname: "127.0.0.1",
  port: 54443,
  tls: {
    key: Bun.file("e2e/private/ingestion-key.pem"),
    cert: Bun.file("e2e/private/ingestion-cert.pem"),
  },
  async fetch(req) {
    c01Requests++;
    envelopes.push({ id: req.headers.get("idempotency-key"), body: await req.clone().json() });
    if (c01Failure === 1) {
      c01Failure = 0;
      return new Response("{}", { status: 503, headers: { "retry-after": "1" } });
    }
    if (c01Failure === 2) {
      c01Failure = 0;
      await ingest(req);
      return new Response("ambiguous", { status: 200 });
    }
    return ingest(req);
  },
});
async function api(user: any, tenant: string, action: string, body?: any, cookie?: string) {
  const r = await fetch(origin + "/api/connected/" + action + (body ? "" : "?tenant=" + tenant), {
    method: body ? "POST" : "GET",
    headers: {
      authorization: "Bearer " + user.access_token,
      origin,
      "content-type": "application/json",
      ...(cookie ? { cookie } : {}),
    },
    ...(body ? { body: JSON.stringify({ ...body, tenant }) } : {}),
  });
  return { status: r.status, data: await r.json(), cookie: r.headers.get("set-cookie") };
}
const context = {
  service: "Synthetic workflow SaaS",
  unit: "organization",
  promise: "Human documented workflow completion",
  sources: "PostHog",
  region: "us",
  consent: true,
};
async function begin(user: any, tenant: string) {
  const start = await api(user, tenant, "start", context);
  eq(start.status, 200);
  const response = await fetch(start.data.authorization, { redirect: "manual" });
  eq(response.status, 302);
  const callback = new URL(response.headers.get("location")!);
  return {
    state: callback.searchParams.get("state"),
    code: callback.searchParams.get("code"),
    cookie: start.cookie!.split(";")[0],
  };
}
async function finish(user: any, tenant: string, s: any) {
  return api(user, tenant, "finish", { state: s.state, code: s.code }, s.cookie);
}
async function dbConnection(tenant: string) {
  return (
    await sql`SELECT * FROM connected_private.connections WHERE tenant_id=${tenant} ORDER BY created_at DESC LIMIT 1`
  )[0];
}
try {
  eq((await api(a, tenantA, "status")).data.status, "not_connected");
  eq((await api(b, tenantA, "status")).status, 403);
  eq((await api(operator, tenantA, "start", context)).status, 403);
  const noAuth = await fetch(origin + "/api/connected/status?tenant=" + tenantA);
  eq(noAuth.status, 401);
  const csrf = await fetch(origin + "/api/connected/start", {
    method: "POST",
    headers: {
      authorization: "Bearer " + a.access_token,
      origin: "https://evil.invalid",
      "content-type": "application/json",
    },
    body: JSON.stringify({ ...context, tenant: tenantA }),
  });
  eq(csrf.status, 403);
  eq((await api(a, tenantA, "start", { ...context, consent: false })).status, 400);
  eq((await api(a, tenantA, "start", { ...context, unit: "person" })).status, 400);
  badIssuer = true;
  eq((await api(a, tenantA, "start", context)).status, 502);
  badIssuer = false;
  const flow = await begin(a, tenantA);
  eq((await finish(b, tenantA, flow)).status, 403);
  eq(
    (
      await api(
        a,
        tenantA,
        "finish",
        { state: flow.state, code: flow.code },
        "cw_posthog_nonce=wrong",
      )
    ).status,
    403,
  );
  eq((await finish(a, tenantA, flow)).status, 200);
  eq((await finish(a, tenantA, flow)).status, 403);
  let summary = (await api(a, tenantA, "status")).data;
  eq(summary.status, "needs_mapping");
  eq(summary.project_id, 41);
  ok(!JSON.stringify(summary).includes("access_token"));
  const c = await dbConnection(tenantA);
  ok(c.secret_cipher.startsWith("v1."));
  ok(!c.secret_cipher.includes("access_token"));
  const clear = unseal<any>(c.secret_cipher, cfg.key, `${tenantA}:${c.id}:tokens`);
  ok(clear.access_token);
  assert.throws(() => unseal(c.secret_cipher, cfg.key, `${tenantB}:${c.id}:tokens`));
  assertions++;
  const actorA = {
    sub: a.user.id,
    session_id: JSON.parse(Buffer.from(a.access_token.split(".")[1], "base64url").toString())
      .session_id,
  };
  await connector.store.actor(tenantA, actorA, false, async (db) => {
    eq(
      (
        await db`SELECT count(*)::int AS n FROM connected_private.connections WHERE tenant_id=${tenantB}`
      )[0].n,
      0,
    );
  });
  const denied = await fetch(pub.url + "/rest/v1/connections", {
    headers: { apikey: pub.anon, authorization: "Bearer " + a.access_token },
  });
  eq(denied.status, 404);
  badPage = true;
  eq((await api(a, tenantA, "discover", { group_type_index: 0 })).status, 502);
  badPage = false;
  rate = true;
  eq((await api(a, tenantA, "discover", { group_type_index: 0 })).status, 429);
  rate = false;
  eq((await api(a, tenantA, "discover", { group_type_index: 4 })).status, 400);
  eq((await api(a, tenantA, "discover", { group_type_index: 0 })).status, 200);
  summary = (await api(a, tenantA, "status")).data;
  eq(summary.preview.groups.length, 2);
  eq(summary.preview.metrics.length, 1);
  ok(!JSON.stringify(summary).includes("stable-acme"));
  ok(!JSON.stringify(summary).includes("never-persist"));
  const refs = summary.preview.groups.map((g: any) => g.ref);
  eq((await api(a, tenantA, "discover", { group_type_index: 0 })).status, 200);
  eq(
    (await api(a, tenantA, "status")).data.preview.groups.map((g: any) => g.ref),
    refs,
  );
  eq((await api(a, tenantA, "sync", {})).status, 409);
  eq((await sql`SELECT count(*)::int AS n FROM subjects WHERE tenant_id=${tenantA}`)[0].n, 0);
  const start = new Date(Date.now() - 3 * 86400000).toISOString().slice(0, 10);
  const selection = {
    confirmed: true,
    start,
    groups: summary.preview.groups,
    metrics: [
      {
        ...summary.preview.metrics[0],
        classification: "outcome",
        direction: "higher_is_better",
        target_value: 20,
      },
    ],
  };
  eq(
    (await api(a, tenantA, "prepare", { selection: { ...selection, confirmed: false } })).status,
    400,
  );
  eq((await api(a, tenantA, "prepare", { selection })).status, 200);
  eq((await api(a, tenantA, "prepare", { selection })).status, 200);
  eq((await api(a, tenantA, "activate", {})).status, 422);
  const profile = (await dbConnection(tenantA)).profile_id;
  // Deliberately human-supplied test contract. These values are never inferred by discovery.
  await rest(
    a,
    `profile_indicators?tenant_id=eq.${tenantA}&profile_id=eq.${profile}`,
    {
      baseline_method: "fixed_value",
      baseline_value: 10,
      baseline_min_period_days: 1,
      observation_window_days: 1,
      comparison_window_days: 1,
      min_coverage_pct: 100,
      min_denominator: 1,
      deterioration_kind: "absolute",
      deterioration_operator: "lt",
      deterioration_value: 5,
      deterioration_consecutive_windows: 2,
      recovery_kind: "absolute",
      recovery_operator: "gte",
      recovery_value: 10,
      recovery_consecutive_windows: 2,
    },
    "PATCH",
  );
  eq((await api(a, tenantA, "activate", {})).status, 200);
  eq((await api(a, tenantA, "activate", {})).status, 200);
  eq((await sql`SELECT count(*)::int AS n FROM subjects WHERE tenant_id=${tenantA}`)[0].n, 2);
  c01Failure = 1;
  eq((await api(a, tenantA, "sync", {})).status, 503);
  const first = envelopes.at(-1);
  await new Promise((r) => setTimeout(r, 1100));
  eq((await api(a, tenantA, "sync", {})).status, 200);
  eq(envelopes.at(-1).id, first.id);
  eq(envelopes.at(-1).body, first.body);
  eq((await sql`SELECT count(*)::int AS n FROM observations WHERE tenant_id=${tenantA}`)[0].n, 2);
  late = true;
  eq((await api(a, tenantA, "sync", {})).data.rows, 1);
  eq(
    (
      await sql`SELECT count(*)::int AS n FROM observations WHERE tenant_id=${tenantA} AND corrects_observation_id IS NOT NULL`
    )[0].n,
    1,
  );
  eq((await api(a, tenantA, "sync", {})).data.status, "completed");
  eq((await api(a, tenantA, "sync", {})).data.status, "no_op");
  late = false;
  // Forward slice succeeds in C01 but its response is lost. Same request/rows are replayed.
  c01Failure = 2;
  eq((await api(a, tenantA, "sync", {})).status, 503);
  const lost = envelopes.at(-1);
  await new Promise((r) => setTimeout(r, 1100)); // backoff is 60 seconds: test persistence without falsifying clocks.
  const pending =
    await sql`SELECT * FROM connected_private.batches WHERE connection_id=${c.id} AND status='pending'`;
  eq(pending.length, 1);
  eq(pending[0].id, lost.id);
  eq((await api(a, tenantA, "sync", {})).data.status, "backoff");
  // Honour the real retry deadline; no injected clock or shortened product timeout.
  await new Promise((r) => setTimeout(r, 60000));
  eq((await api(a, tenantA, "sync", {})).status, 200);
  eq(envelopes.at(-1).id, lost.id);
  eq(envelopes.at(-1).body, lost.body);
  const beforeRefresh = refreshes;
  let live = await dbConnection(tenantA);
  const token = unseal<any>(live.secret_cipher, cfg.key, `${tenantA}:${live.id}:tokens`);
  token.expires_at = Date.now() - 1000;
  await sql`UPDATE connected_private.connections SET secret_cipher=${seal(token, cfg.key, `${tenantA}:${live.id}:tokens`)} WHERE id=${live.id}`;
  eq((await api(a, tenantA, "sync", {})).status, 200);
  eq(refreshes, beforeRefresh + 1);
  delay = true;
  const concurrent = await Promise.all([api(a, tenantA, "sync", {}), api(a, tenantA, "sync", {})]);
  ok(concurrent.some((r) => r.status === 409));
  delay = false;
  queryFail = true;
  eq((await api(a, tenantA, "sync", {})).status, 502);
  queryFail = false;
  // Tenant B gets its own scoped project, never A's authorization.
  project = 72;
  const bf = await begin(b, tenantB);
  eq((await finish(b, tenantB, bf)).status, 200);
  eq((await api(b, tenantB, "status")).data.project_id, 72);
  eq((await api(a, tenantB, "status")).status, 403);
  await rest(b, "rpc/add_tenant_member", {
    _tenant_id: tenantB,
    _user_id: a.user.id,
    _role: "admin",
  });
  eq((await api(a, tenantB, "status")).data.needs_reauthorization, true);
  eq((await api(a, tenantA, "status")).data.id, c.id);
  await connector.store.actor(tenantA, actorA, false, async (db) => {
    eq(
      (
        await db`SELECT count(*)::int AS n FROM connected_private.connections WHERE tenant_id=${tenantB}`
      )[0].n,
      0,
    );
  });
  const count = (
    await sql`SELECT count(*)::int AS n FROM observations WHERE tenant_id=${tenantA}`
  )[0].n;
  await rest(a, "rpc/set_member_role", {
    _tenant_id: tenantA,
    _user_id: a.user.id,
    _role: "operator",
  }).catch(() => {}); // last admin guard is expected; use another admin before loss.
  await rest(a, "rpc/add_tenant_member", {
    _tenant_id: tenantA,
    _user_id: b.user.id,
    _role: "admin",
  });
  await rest(b, "rpc/set_member_role", {
    _tenant_id: tenantA,
    _user_id: a.user.id,
    _role: "operator",
  });
  eq((await api(a, tenantA, "sync", {})).status, 403);
  eq((await dbConnection(tenantA)).status, "revoked");
  eq(
    (
      await sql`SELECT revoked_at IS NOT NULL AS revoked FROM ingestion_credentials WHERE id=${live.credential_id}`
    )[0].revoked,
    true,
  );
  await rest(b, "rpc/set_member_role", {
    _tenant_id: tenantA,
    _user_id: a.user.id,
    _role: "admin",
  });
  eq((await api(a, tenantA, "sync", {})).status, 409);
  eq(
    (await sql`SELECT count(*)::int AS n FROM observations WHERE tenant_id=${tenantA}`)[0].n,
    count,
  );
  await connector.revokeQueued();
  ok(revocations >= 1);
  const bc=await dbConnection(tenantB);const bt=unseal<any>(bc.secret_cipher,cfg.key,`${tenantB}:${bc.id}:tokens`);bt.expires_at=Date.now()-1;await sql`UPDATE connected_private.connections SET secret_cipher=${seal(bt,cfg.key,`${tenantB}:${bc.id}:tokens`)} WHERE id=${bc.id}`;
  refreshFail=true;eq((await api(b,tenantB,'discover',{group_type_index:0})).status,502);eq((await dbConnection(tenantB)).status,'failed');refreshFail=false;
  eq((await api(b, tenantB, "disconnect", {})).status, 200);
  eq((await api(b, tenantB, "status")).data.status, "revoked");
  broad = true;
  const bad = await begin(b, tenantB);
  eq((await finish(b, tenantB, bad)).status, 403);
  broad = false;
  await api(b, tenantB, "disconnect", {});
  const expired = await begin(b, tenantB);
  await sql`UPDATE connected_private.oauth_states SET expires_at=clock_timestamp()-interval '1 second' WHERE state_hash=${digest(expired.state!)}`;
  eq((await finish(b, tenantB, expired)).status, 403);
  await api(b, tenantB, "disconnect", {});
  eq((await connector.worker()).length,0); // Manual invocation only; no real hosted scheduler.
  const tableCounts: any = {};
  for (const name of [
    "c02_runs",
    "c03_bundles",
    "c04_evaluations",
    "cw_cases",
    "cw_operational_cases",
  ]) {
    tableCounts[name] = Number(
      (
        await sql.unsafe(`SELECT count(*) AS n FROM public.${name} WHERE tenant_id IN ($1,$2)`, [
          tenantA,
          tenantB,
        ])
      )[0].n,
    );
    eq(tableCounts[name], 0);
  }
  const obs = (await sql`SELECT count(*)::int AS n FROM observations WHERE tenant_id=${tenantA}`)[0]
    .n;
  await Bun.write(
    "e2e/logs/connected-results.json",
    JSON.stringify(
      {
        posthog: "controlled OAuth/HTTP mock; no hosted authorization",
        auth: "real GoTrue password grants",
        database: "disposable PostgreSQL17, real RLS; runtime dedicated NOINHERIT role",
        assertions,
        subjects: 2,
        observations: obs,
        c01Requests,
        refreshes,
        revocations,
        providerCalls,
        automaticCore: tableCounts,
      },
      null,
      2,
    ),
  );
  console.log(
    `Connected onboarding: ${assertions} assertions passed; ${obs} persisted observations; ${c01Requests} C01 HTTP attempts. PostHog MOCK only.`,
  );
  if (process.argv.includes("--serve")) {
    const tenantUI = await rest(a, "rpc/create_tenant", {
      _name: "Connected browser " + run,
      _subject_unit_type: "organization",
    });
    await Bun.write(
      "e2e/private/connected-browser.json",
      JSON.stringify({
        tenant: tenantUI,tenantName:"Connected browser "+run,tenantBName:"Connected B "+run,
        tenantB,
        user: { email: a.user.email, password },
        operator: { email: operator.user.email, password },
      }),
    );
    const runtime = Object.fromEntries(
      Object.entries(process.env).filter(
        ([k]) => k.startsWith("CW_") || ["SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"].includes(k),
      ),
    );
    runtime.CW_CONNECTOR_ORIGIN = "http://127.0.0.1:5173";
    runtime.CW_POSTHOG_CLIENT_ID = "http://127.0.0.1:5173/api/connected/metadata";
    await Bun.write("e2e/private/connected-runtime.json", JSON.stringify(runtime));
    console.log("Controlled OAuth provider ready for browser tests; no hosted requests.");
    await new Promise<void>((resolve) => {
      process.once("SIGTERM", () => resolve());
      process.once("SIGINT", () => resolve());
    });
  }
} finally {
  mock.stop(true);
  app.stop(true);
  c01.stop(true);
  await connector.store.sql.end();
  await sql.end();
}
