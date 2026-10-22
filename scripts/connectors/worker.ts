/** Opt-in worker; installation never schedules this automatically. No hosted calls without explicit runtime configuration. */
import { Connector } from "../../src/server/connected/service";
import { config } from "../../src/server/connected/security";
if (!process.argv.includes("--once"))
  throw new Error("Use --once; external scheduler must serialize invocations.");
const connector = new Connector(config());
try {
  console.log(JSON.stringify(await connector.worker()));
} finally {
  await connector.store.sql.end({timeout:2});
}
