/** Shared by the Supabase Edge Function and the disposable HTTPS test server. */
export function ingestionHandler(config: { url: string; anonKey: string; fetch?: typeof fetch }) {
  const transport = config.fetch ?? fetch;
  return async (request: Request): Promise<Response> => {
    const requestId = crypto.randomUUID();
    const reply = (status: number, body: unknown, retry?: string) => {
      // Never log headers, body, integration keys or upstream errors.
      if (status >= 400)
        console.warn(
          JSON.stringify({ event: "ingestion_rejected", status, request_id: requestId }),
        );
      return new Response(JSON.stringify(body), {
        status,
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
          "X-Request-ID": requestId,
          ...(retry ? { "Retry-After": retry } : {}),
        },
      });
    };
    if (!new URL(request.url).pathname.endsWith("/ingest-v1/observations"))
      return reply(404, { code: "not_found" });
    if (request.method !== "POST") return reply(405, { code: "method_not_allowed" });
    const credential = request.headers
      .get("authorization")
      ?.match(/^Bearer (cw_ingest_v1_[0-9a-f-]{36}\.[0-9a-f]{64})$/)?.[1];
    if (!credential) return reply(401, { code: "credential_invalid" });
    const operation = request.headers.get("idempotency-key");
    if (
      !operation ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(operation)
    )
      return reply(400, { code: "idempotency_key_required" });
    if (
      request.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase() !==
        "application/json" ||
      (request.headers.get("content-encoding") ?? "identity") !== "identity"
    )
      return reply(415, { code: "unsupported_media_type" });
    if (Number(request.headers.get("content-length")) > 2_000_000)
      return reply(413, { code: "payload_too_large" });
    let payload: unknown;
    try {
      const reader = request.body?.getReader();
      if (!reader) return reply(400, { code: "invalid_json" });
      const chunks: Uint8Array[] = [];
      let length = 0;
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        length += part.value.byteLength;
        if (length > 2_000_000) {
          await reader.cancel();
          return reply(413, { code: "payload_too_large" });
        }
        chunks.push(part.value);
      }
      const bytes = new Uint8Array(length);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.length;
      }
      payload = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    } catch {
      return reply(400, { code: "invalid_json" });
    }
    try {
      const upstream = await transport(
        `${config.url.replace(/\/$/, "")}/rest/v1/rpc/ingest_external_observations`,
        {
          method: "POST",
          headers: {
            apikey: config.anonKey,
            Authorization: `Bearer ${config.anonKey}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            _credential: credential,
            _operation_id: operation,
            _payload: payload,
          }),
          signal: AbortSignal.timeout(30_000),
        },
      );
      if (!upstream.ok) return reply(503, { code: "ingestion_unavailable", request_id: requestId });
      const result = (await upstream.json()) as {
        http_status: number;
        body: Record<string, unknown>;
        retry_after?: number;
      };
      if (![200, 400, 401, 409, 413, 422, 429].includes(result.http_status))
        return reply(503, { code: "ingestion_unavailable" });
      return reply(
        result.http_status,
        { ...result.body, request_id: requestId },
        typeof result.body["retry_after"] === "number"
          ? String(result.body["retry_after"])
          : undefined,
      );
    } catch {
      return reply(503, { code: "ingestion_unavailable", request_id: requestId });
    }
  };
}
