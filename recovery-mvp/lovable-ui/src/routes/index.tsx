import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    throw redirect({ to: "/app" });
  },
  head: () => ({
    meta: [
      { title: "CENTERWAY — Inteligência de valor do cliente" },
      { name: "description", content: "Demonstração da interface CENTERWAY para acompanhar o valor entregue a clientes SaaS." },
      { property: "og:title", content: "CENTERWAY — Inteligência de valor do cliente" },
      { property: "og:description", content: "Demonstração da interface CENTERWAY para acompanhar o valor entregue a clientes SaaS." },
    ],
  }),
});

