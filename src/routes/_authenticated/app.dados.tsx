import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useTenant, tk } from "@/lib/tenant";
import { countQuery } from "@/lib/queries";
import { Empty, ErrorState, formatDate, Loading, PageHeader, Panel, StatusPill } from "@/components/app/ui-bits";

export const Route = createFileRoute("/_authenticated/app/dados")({
  head: () => ({
    meta: [
      { title: "Dados — CENTERWAY" },
      { name: "description", content: "Lotes de dados e observações registadas." },
      { property: "og:title", content: "Dados — CENTERWAY" },
      { property: "og:description", content: "Lotes de dados e observações registadas." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Dados,
});

const batchStatus = { received: "Recebido", processing: "Em processamento", completed: "Concluído", failed: "Falhou" } as const;

function Dados() {
  const { tenant } = useTenant();
  const obs = useQuery(countQuery(tenant.id, "observations"));
  const batches = useQuery({
    queryKey: tk(tenant.id, "batches"),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("ingestion_batches")
        .select("id, source, status, coverage_start, coverage_end, created_at")
        .eq("tenant_id", tenant.id)
        .order("created_at", { ascending: false })
        .limit(50);
      if (error) throw error;
      return data ?? [];
    },
  });

  return (
    <>
      <PageHeader title="Dados" description="Origem das observações usadas como evidência. As observações nunca são alteradas; correções são novos registos." />
      <div className="space-y-6">
        <Panel title="Importação">
          <p className="text-sm text-muted-foreground">Disponível numa próxima etapa. Ainda não é possível importar ficheiros ou ligar fontes.</p>
        </Panel>
        <Panel title={`Lotes recebidos${obs.data !== undefined ? ` · ${obs.data} observações` : ""}`}>
          {batches.isLoading ? (
            <Loading />
          ) : batches.isError ? (
            <ErrorState message="Não foi possível carregar os lotes." onRetry={() => batches.refetch()} />
          ) : batches.data!.length === 0 ? (
            <Empty title="Sem lotes de dados">Quando a importação estiver disponível, os lotes aparecem aqui.</Empty>
          ) : (
            <ul className="divide-y divide-border text-sm">
              {batches.data!.map((b) => (
                <li key={b.id} className="flex flex-wrap items-center gap-3 py-2">
                  <span className="font-medium">{b.source}</span>
                  <StatusPill tone={b.status === "failed" ? "neutral" : "muted"}>{batchStatus[b.status]}</StatusPill>
                  <span className="text-muted-foreground">
                    {formatDate(b.coverage_start)} → {formatDate(b.coverage_end)}
                  </span>
                  <span className="ml-auto text-xs text-muted-foreground">{formatDate(b.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
