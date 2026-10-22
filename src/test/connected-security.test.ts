import { afterEach, describe, expect, it, vi } from "vitest";
import { randomBytes } from "node:crypto";
import {
  challenge,
  config,
  digest,
  literal,
  seal,
  unseal,
  validScopes,
  type Config,
} from "../server/connected/security";
import { eventQuery, PostHog } from "../server/connected/posthog";
const cfg: Config = {
  origin: "https://centerway.example",
  clientId: "https://centerway.example/api/connected/metadata",
  redirect: "https://centerway.example/posthog/callback",
  authUrl: "https://db.example",
  publicKey: "public",
  database: "postgres://runtime@db/centerway",
  key: randomBytes(32),
  c01: "https://db.example/functions/v1/ingest-v1/observations",
  local: false,
};
afterEach(() => vi.unstubAllGlobals());
describe("connected onboarding security boundaries", () => {
  it("encrypts nondeterministically, binds tenant/connection/purpose, rejects tampering and wrong key", () => {
    const secret = { access_token: "synthetic-only", refresh_token: "synthetic-refresh" };
    const a = seal(secret, cfg.key, "A:connection:tokens"),
      b = seal(secret, cfg.key, "A:connection:tokens");
    expect(a).not.toBe(b);
    expect(a).not.toContain(secret.access_token);
    expect(unseal(a, cfg.key, "A:connection:tokens")).toEqual(secret);
    expect(() => unseal(a, cfg.key, "B:connection:tokens")).toThrow();
    expect(() => unseal(a, randomBytes(32), "A:connection:tokens")).toThrow();
    expect(() => unseal(a.slice(0, -3) + "abc", cfg.key, "A:connection:tokens")).toThrow();
    expect(() => unseal("cleartext", cfg.key, "A")).toThrow();
  });
  it("requires exactly the minimum scopes, no writes or optional scope widening", () => {
    expect(validScopes("project:read query:read group:read")).toBe(true);
    for (const s of [
      "project:read query:read",
      "project:read query:read group:read user:read",
      "project:read query:read group:write",
      "project:read query:read group:read group:read",
    ])
      expect(validScopes(s)).toBe(false);
  });
  it("uses RFC7636 S256 and stable hashes without treating a key as OAuth", () => {
    expect(challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
      "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    );
    expect(digest("a")).toHaveLength(64);
  });
  it("fails closed with missing runtime configuration, service-role or unsafe test endpoints", () => {
    expect(() => config({})).toThrow("connector_not_configured");
    const env = {
      CW_CONNECTOR_ORIGIN: cfg.origin,
      CW_POSTHOG_CLIENT_ID: cfg.clientId,
      CW_CONNECTOR_DATABASE_URL: cfg.database,
      CW_CONNECTOR_KEY: cfg.key.toString("base64"),
      SUPABASE_URL: cfg.authUrl,
      SUPABASE_PUBLISHABLE_KEY: "public",
      CW_C01_URL: cfg.c01,
    };
    expect(config(env).local).toBe(false);
    expect(() => config({ ...env, CW_POSTHOG_MOCK: "http://127.0.0.1:9000" })).toThrow(
      "mock_forbidden",
    );
    expect(() => config({ ...env, SUPABASE_PUBLISHABLE_KEY: "sb_secret_forbidden" })).toThrow();
    expect(() => config({ ...env, CW_CONNECTOR_KEY: "short" })).toThrow();
    expect(() => config({ ...env, CW_C01_URL: "http://internal/" })).toThrow();
    expect(() =>
      config({ ...env, CW_POSTHOG_CLIENT_ID: "https://user:password@host/client" }),
    ).toThrow();
  });
  it("never permits a user-provided PostHog host or a foreign project path", async () => {
    expect(() => new PostHog(cfg, "attacker")).toThrow();
    const p = new PostHog(cfg, "eu");
    await expect(
      p.get("/api/projects/99/", {
        project: 1,
        access_token: "x",
        refresh_token: "r",
        expires_at: 0,
      }),
    ).rejects.toThrow("project_path_invalid");
  });
  it("rejects issuer or endpoint drift before authorization, without following redirects", async () => {
    const fetch = vi.fn(async (_u: any, init: any) => {
      expect(init.redirect).toBe("error");
      return Response.json({
        issuer: "https://evil.invalid",
        code_challenge_methods_supported: ["S256"],
        response_types_supported: ["code"],
      });
    });
    vi.stubGlobal("fetch", fetch);
    await expect(new PostHog(cfg, "us").authorization("s", "n", "v")).rejects.toThrow(
      "oauth_metadata_invalid",
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("bounds streamed responses and rejects invalid JSON", async () => {
    const { jsonFetch } = await import("../server/connected/security");
    vi.stubGlobal("fetch", async () => new Response("123456789"));
    await expect(jsonFetch("https://us.posthog.com", {}, 5)).rejects.toThrow("response_too_large");
    vi.stubGlobal("fetch", async () => new Response("not json"));
    await expect(jsonFetch("https://us.posthog.com")).rejects.toThrow("invalid_response");
  });
  it("constructs only an aggregate query and escapes group/event literals", () => {
    const q = eventQuery("company'\\", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", [
      "done'); DROP TABLE events; --",
    ]);
    expect(q).toContain("count() AS amount");
    expect(q).toContain("LIMIT 10001");
    expect(q).not.toContain("distinct_id");
    expect(literal("a'b\\c")).toBe("'a\\'b\\\\c'");
  });
});
