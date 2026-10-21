// Local test harness only. The production entrypoint remains Deno.serve in supabase/functions.
import { ingestionHandler } from "../supabase/functions/_shared/ingestion-handler";
const cfg = await Bun.file("e2e/private/public.json").json();
if (cfg.url !== "http://127.0.0.1:54321") throw Error("Disposable loopback backend required");
Bun.serve({
  hostname: "127.0.0.1",
  port: 54443,
  // Allow the real C01 upstream deadline (30s) to produce its documented 503.
  idleTimeout: 40,
  tls: {
    key: Bun.file("e2e/private/ingestion-key.pem"),
    cert: Bun.file("e2e/private/ingestion-cert.pem"),
  },
  fetch: ingestionHandler({ url: cfg.url, anonKey: cfg.anon }),
});
console.log("Disposable HTTPS ingestion endpoint ready on loopback.");
