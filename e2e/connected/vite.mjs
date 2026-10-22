import { spawn } from "node:child_process";
import fs from "node:fs";
const runtime = JSON.parse(fs.readFileSync("e2e/private/connected-runtime.json"));
const child = spawn(
  "bun",
  ["run", "dev", "--config", "e2e/vite.config.ts", "--host", "127.0.0.1", "--port", "5173"],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      ...runtime,
      NODE_EXTRA_CA_CERTS: process.cwd() + "/e2e/private/ingestion-cert.pem",
    },
  },
);
for (const signal of ["SIGTERM", "SIGINT"]) process.on(signal, () => child.kill(signal));
child.on("exit", (code) => process.exit(code || 0));
