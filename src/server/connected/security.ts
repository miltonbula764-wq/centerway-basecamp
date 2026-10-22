import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
  timingSafeEqual,
} from "node:crypto";

export class ConnectorError extends Error {
  constructor(
    public code: string,
    public status = 400,
    public retryAfter = 60,
  ) {
    super(code);
  }
}
export const scopes = ["group:read", "project:read", "query:read"];
export const digest = (s: string) => createHash("sha256").update(s).digest("hex");
export const random = () => randomBytes(32).toString("base64url");
export const challenge = (s: string) => createHash("sha256").update(s).digest("base64url");
export function same(a: string, b: string) {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}
export function seal(value: unknown, key: Buffer, aad: string) {
  const iv = randomBytes(12);
  const c = createCipheriv("aes-256-gcm", key, iv);
  c.setAAD(Buffer.from(aad));
  return [
    "v1",
    iv.toString("base64url"),
    Buffer.concat([c.update(JSON.stringify(value)), c.final()]).toString("base64url"),
    c.getAuthTag().toString("base64url"),
  ].join(".");
}
export function unseal<T>(value: string, key: Buffer, aad: string): T {
  const [v, iv, data, tag, extra] = value.split(".");
  if (v !== "v1" || extra || !iv || !data || !tag) throw new ConnectorError("cipher_invalid", 503);
  const c = createDecipheriv("aes-256-gcm", key, Buffer.from(iv, "base64url"));
  c.setAAD(Buffer.from(aad));
  c.setAuthTag(Buffer.from(tag, "base64url"));
  return JSON.parse(
    Buffer.concat([c.update(Buffer.from(data, "base64url")), c.final()]).toString(),
  );
}
export type Config = {
  origin: string;
  clientId: string;
  redirect: string;
  authUrl: string;
  publicKey: string;
  database: string;
  key: Buffer;
  c01: string;
  local: boolean;
  mock?: string | undefined;
};
export function config(env = process.env): Config {
  const required = [
    "CW_CONNECTOR_ORIGIN",
    "CW_POSTHOG_CLIENT_ID",
    "CW_CONNECTOR_DATABASE_URL",
    "CW_CONNECTOR_KEY",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "CW_C01_URL",
  ];
  if (required.some((k) => !env[k])) throw new ConnectorError("connector_not_configured", 503);
  const key = Buffer.from(env["CW_CONNECTOR_KEY"]!, "base64");
  if (key.length !== 32 || env["SUPABASE_PUBLISHABLE_KEY"]!.startsWith("sb_secret_"))
    throw new ConnectorError("connector_configuration_invalid", 503);
  try {
    if (
      JSON.parse(
        Buffer.from(env["SUPABASE_PUBLISHABLE_KEY"]!.split(".")[1] || "", "base64url").toString(),
      ).role === "service_role"
    )
      throw new ConnectorError("service_role_forbidden", 503);
  } catch (e) {
    if (e instanceof ConnectorError) throw e;
  }
  const local =
    env["CW_LOCAL_MVP"] === "1" &&
    new URL(env["CW_CONNECTOR_DATABASE_URL"]!).hostname === "127.0.0.1" &&
    new URL(env["CW_CONNECTOR_DATABASE_URL"]!).pathname === "/cw_e2e";
  for (const k of ["CW_CONNECTOR_ORIGIN", "CW_POSTHOG_CLIENT_ID", "SUPABASE_URL", "CW_C01_URL"]) {
    const u = new URL(env[k]!);
    if (
      u.username ||
      u.password ||
      u.hash ||
      u.search ||
      (u.protocol !== "https:" && !(local && u.hostname === "127.0.0.1" && u.protocol === "http:"))
    )
      throw new ConnectorError("connector_url_invalid", 503);
  }
  const origin = new URL(env["CW_CONNECTOR_ORIGIN"]!).origin;
  if (
    new URL(env["CW_POSTHOG_CLIENT_ID"]!).origin !== origin ||
    new URL(env["CW_POSTHOG_CLIENT_ID"]!).pathname !== "/api/connected/metadata"
  )
    throw new ConnectorError("cimd_url_invalid", 503);
  if (
    env["CW_POSTHOG_MOCK"] &&
    (!local || new URL(env["CW_POSTHOG_MOCK"]).hostname !== "127.0.0.1")
  )
    throw new ConnectorError("mock_forbidden", 503);
  return {
    origin,
    clientId: env["CW_POSTHOG_CLIENT_ID"]!,
    redirect: origin + "/posthog/callback",
    authUrl: env["SUPABASE_URL"]!.replace(/\/$/, ""),
    publicKey: env["SUPABASE_PUBLISHABLE_KEY"]!,
    database: env["CW_CONNECTOR_DATABASE_URL"]!,
    key,
    c01: env["CW_C01_URL"]!,
    local,
    mock: env["CW_POSTHOG_MOCK"],
  };
}
export const uuid = (s: unknown): s is string =>
  typeof s === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(s);
export async function jsonFetch(url: string, init: RequestInit = {}, max = 1_000_000) {
  let r: Response;
  try {
    r = await fetch(url, { ...init, redirect: "error", signal: AbortSignal.timeout(15_000) });
  } catch {
    throw new ConnectorError("transport_unavailable", 503);
  }
  if (!r.ok)
    throw new ConnectorError(
      r.status === 429
        ? "provider_rate_limited"
        : r.status === 401 || r.status === 403
          ? "provider_authorization_lost"
          : "provider_error",
      r.status === 429 ? 429 : r.status === 401 || r.status === 403 ? 401 : 502,
      Math.min(3600, Math.max(1, Number(r.headers.get("retry-after")) || 60)),
    );
  const reader = r.body?.getReader();
  let size = 0;
  const chunks: Uint8Array[] = [];
  if (!reader) throw new ConnectorError("empty_response", 502);
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > max) {
      await reader.cancel();
      throw new ConnectorError("response_too_large", 502);
    }
    chunks.push(value);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString());
  } catch {
    throw new ConnectorError("invalid_response", 502);
  }
}
// SQL literals only, never identifiers or arbitrary query text supplied by the browser.
export const literal = (s: string) => "'" + s.replace(/\\/g, "\\\\").replace(/'/g, "\\'") + "'";
export function validScopes(value: unknown) {
  return (
    typeof value === "string" &&
    value.split(/\s+/).filter(Boolean).sort().join(" ") === scopes.join(" ")
  );
}
