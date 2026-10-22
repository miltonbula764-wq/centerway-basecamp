/** Optional backend for runtimes with PostgreSQL TCP/TLS support; reverse proxy on product origin. */
import { handler } from "../../src/server/connected/service";
const port = Number(process.env.CW_CONNECTOR_PORT || 3005);
if (!Number.isSafeInteger(port) || port < 1024 || port > 65535)
  throw new Error("Invalid connector port");
Bun.serve({ hostname: "127.0.0.1", port, fetch: handler, idleTimeout: 45 });
console.log("Connector backend listening on loopback; runtime configuration remains required.");
