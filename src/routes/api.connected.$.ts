import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/api/connected/$")({
  server: {
    handlers: {
      GET: async ({ request }) => (await import("@/server/connected/service")).handler(request),
      POST: async ({ request }) => (await import("@/server/connected/service")).handler(request),
    },
  },
});
