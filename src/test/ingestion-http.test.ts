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

describe("bounded body and ambiguous commit recovery", () => {
  it("expires an unfinished body without waiting for its cancellation and never contacts SQL", async () => {
    const upstream = vi.fn();
    const cancel = vi.fn(() => new Promise<void>(() => {}));
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(new TextEncoder().encode("{"));
      },
      cancel,
    });
    const req = new Request(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${credential}`,
        "Idempotency-Key": id,
        "Content-Type": "application/json",
      },
      body: stream,
      duplex: "half",
    } as RequestInit);
    const result = await ingestionHandler({
      url: "https://api.invalid",
      anonKey: "public",
      fetch: upstream,
      bodyTimeoutMs: 15,
    })(req);
    expect(result.status).toBe(408);
    expect(cancel).toHaveBeenCalled();
    expect(upstream).not.toHaveBeenCalled();
    expect((await result.json()).code).toBe("request_body_timeout");
  });
  it("rejects an already aborted upload without executing an import", async () => {
    const c = new AbortController();
    c.abort();
    const upstream = vi.fn();
    const req = new Request(request(), { signal: c.signal });
    const r = await ingestionHandler({
      url: "https://api.invalid",
      anonKey: "public",
      fetch: upstream,
    })(req);
    expect(r.status).toBe(408);
    expect(upstream).not.toHaveBeenCalled();
  });
  it("correlates safe metadata and explicitly preserves the operation identity on an uncertain upstream result", async () => {
    const log = vi.spyOn(console, "info").mockImplementation(() => {});
    try {
      const handler = ingestionHandler({
        url: "https://api.invalid",
        anonKey: "public",
        fetch: vi.fn().mockRejectedValue(new Error(credential)),
      });
      const r = await handler(request());
      const b = await r.json();
      expect(r.status).toBe(503);
      expect(b.retry_same_idempotency_key).toBe(true);
      expect(r.headers.get("retry-after")).toBe("1");
      expect(b.request_id).toBe(r.headers.get("x-request-id"));
      const meta = JSON.parse(log.mock.calls.at(-1)![0]);
      expect(meta.operation_id).toBe(id);
      expect(meta.duration_ms).toBeGreaterThanOrEqual(0);
      expect(JSON.stringify(log.mock.calls)).not.toContain(credential);
    } finally {
      log.mockRestore();
    }
  });
});
