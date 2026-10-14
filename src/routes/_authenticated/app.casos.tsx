import { createFileRoute } from "@tanstack/react-router";
import { PageHeader, Empty } from "@/components/app/ui-bits";

export const Route = createFileRoute("/_authenticated/app/casos")({
  head: () => ({
    meta: [
      { title: "Casos — CENTERWAY" },
      { name: "description", content: "Casos de deterioração de valor (próxima etapa)." },
      { property: "og:title", content: "Casos — CENTERWAY" },
      { property: "og:description", content: "Casos de deterioração de valor (próxima etapa)." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <>
      <PageHeader title="Casos" description="Clientes com deterioração detetada, evidências, impedimento e intervenção." />
      <Empty title="Disponível numa próxima etapa">
        A deteção, análise e intervenção ainda não estão construídas. Não existem casos reais nem de demonstração.
      </Empty>
    </>
  ),
});
