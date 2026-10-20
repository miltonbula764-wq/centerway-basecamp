import { describe, it, expect, vi } from "vitest";
import { ingestionHandler } from "../../supabase/functions/_shared/ingestion-handler";
const credential = `cw_ingest_v1_11111111-1111-4111-8111-111111111111.${"a".repeat(64)}`;
const id = "11111111-1111-4111-8111-111111111111";
const url = "https://example.invalid/functions/v1/ingest-v1/observations";
function request(body = "{}", headers: Record<string, string> = {}) {
  return new Request(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${credential}`,
      "Idempotency-Key": id,
      "Content-Type": "application/json",
      ...headers,
    },
    body,
  });
}
describe("ingestion HTTP transport boundary (controlled upstream, no auth/database claim)", () => {
  it("uses only the public anonymous key upstream and forwards the opaque integration identity to the narrow RPC", async () => {
    const upstream = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ http_status: 200, body: { batch_id: id, status: "completed" } }),
        ),
      );
    const handler = ingestionHandler({
      url: "https://api.invalid",
      anonKey: "public-anon",
      fetch: upstream,
    });
    const r = await handler(request());
    expect(r.status).toBe(200);
    const [target, init] = upstream.mock.calls[0]!;
    expect(target).toBe("https://api.invalid/rest/v1/rpc/ingest_external_observations");
    expect(init.headers.Authorization).toBe("Bearer public-anon");
    expect(JSON.parse(init.body)).toEqual({
      _credential: credential,
      _operation_id: id,
      _payload: {},
    });
    expect(await r.text()).not.toContain(credential);
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect(r.headers.has("access-control-allow-origin")).toBe(false);
  });
  it("rejects invalid headers, content, invalid UTF8/JSON, oversized bodies and methods before contacting the database", async () => {
    const upstream = vi.fn();
    const handler = ingestionHandler({
      url: "https://api.invalid",
      anonKey: "public",
      fetch: upstream,
    });
    for (const [req, status] of [
      [request("{}", { Authorization: "Bearer wrong" }), 401],
      [request("{}", { "Idempotency-Key": "" }), 400],
      [request("{}", { "Content-Type": "text/plain" }), 415],
      [request("{}", { "Content-Encoding": "gzip" }), 415],
      [request("{invalid"), 400],
      [request("x".repeat(2_000_001)), 413],
      [request("{}", { "Content-Length": "2000001" }), 413],
      [new Request(url), 405],
      [new Request("https://example.invalid/other"), 404],
    ] as const)
      expect((await handler(req)).status).toBe(status);
    expect(upstream).not.toHaveBeenCalled();
  });
  it("returns safe upstream failures and Retry-After without echoing SQL errors or credentials", async () => {
    const upstream = vi
      .fn()
      .mockResolvedValueOnce(new Response("SQL private details", { status: 500 }))
      .mockRejectedValueOnce(new Error(credential))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ http_status: 429, body: { code: "rate_limited", retry_after: 42 } }),
        ),
      );
    const handler = ingestionHandler({
      url: "https://api.invalid",
      anonKey: "public",
      fetch: upstream,
    });
    for (let i = 0; i < 2; i++) {
      const r = await handler(request());
      expect(r.status).toBe(503);
      expect(await r.text()).toContain("ingestion_unavailable");
    }
    const limited = await handler(request());
    expect(limited.status).toBe(429);
    expect(limited.headers.get("retry-after")).toBe("42");
  });
});
