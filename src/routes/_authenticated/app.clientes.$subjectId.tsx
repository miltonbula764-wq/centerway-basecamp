import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeft, Pencil } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { tk, useTenant } from "@/lib/tenant";
import { indicatorsQuery, profilesQuery } from "@/lib/queries";
import { classLabel } from "@/lib/profile";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, formatDate, Loading, Mono, PageHeader, Panel, StatusPill } from "@/components/app/ui-bits";
import { SubjectDialog } from "@/components/app/subject-dialog";
import { DeteriorationPanel } from "@/components/app/deterioration-panel";
import { EvidencePanel } from "@/components/app/evidence-panel";

export const Route = createFileRoute("/_authenticated/app/clientes/$subjectId")({
  head: () => ({
    meta: [
      { title: "Cliente — CENTERWAY" },
      { name: "description", content: "Identidade, perfil herdado e observações do cliente." },
      { property: "og:title", content: "Cliente — CENTERWAY" },
      { property: "og:description", content: "Identidade, perfil herdado e observações do cliente." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: ClienteDetalhe,
});

function ClienteDetalhe() {
  const { subjectId } = Route.useParams();
  const { tenant, canWrite } = useTenant();
  const [edit, setEdit] = useState(false);

  const subject = useQuery({
    queryKey: tk(tenant.id, "subject", subjectId),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("subjects")
        .select("id, external_ref, display_name, created_at, updated_at")
        .eq("tenant_id", tenant.id)
        .eq("id", subjectId)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });
  const observations = useQuery({
    queryKey: tk(tenant.id, "observations", subjectId),
    enabled: !!subject.data,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("observations")
        .select("id, indicator_key, value_numeric, value_text, unit, source, observed_at, ingested_at, corrects_observation_id")
        .eq("tenant_id", tenant.id)
        .eq("subject_id", subjectId)
        .order("observed_at", { ascending: false })
        .limit(100);
      if (error) throw error;
      return data ?? [];
    },
  });
  const profiles = useQuery(profilesQuery(tenant.id));
  const approved = profiles.data?.find((p) => p.status === "approved");
  const indicators = useQuery({ ...indicatorsQuery(tenant.id, approved?.id ?? ""), enabled: !!approved });

  if (subject.isLoading) return <Loading />;
  if (subject.isError) return <ErrorState message="Não foi possível carregar o cliente." onRetry={() => subject.refetch()} />;
  if (!subject.data)
    return (
      <Empty title="Cliente não encontrado">
        Não existe nesta empresa ou não tem acesso.{" "}
        <Link to="/app/clientes" className="underline">Voltar à lista</Link>
      </Empty>
    );
  const s = subject.data;

  return (
    <>
      <Link to="/app/clientes" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Clientes
      </Link>
      <PageHeader
        title={s.display_name || s.external_ref}
        actions={canWrite && (
          <Button variant="secondary" onClick={() => setEdit(true)}>
            <Pencil className="h-4 w-4" /> Editar
          </Button>
        )}
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 [&>*]:min-w-0">
        <Panel title="Identidade">
          <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-sm">
            <dt className="text-muted-foreground">Referência externa</dt>
            <dd><Mono>{s.external_ref}</Mono></dd>
            <dt className="text-muted-foreground">Nome</dt>
            <dd>{s.display_name || "—"}</dd>
            <dt className="text-muted-foreground">Tipo</dt>
            <dd>{tenant.subject_unit_type === "person" ? "Pessoa" : "Organização"}</dd>
            <dt className="text-muted-foreground">Criado</dt>
            <dd>{formatDate(s.created_at)}</dd>
            <dt className="text-muted-foreground">Atualizado</dt>
            <dd>{formatDate(s.updated_at)}</dd>
          </dl>
        </Panel>
        <Panel title="Perfil de valor herdado">
          {profiles.isLoading ? (
            <Loading />
          ) : !approved ? (
            <p className="text-sm text-muted-foreground">A empresa ainda não tem um perfil de valor aprovado.</p>
          ) : (
            <div className="space-y-3 text-sm">
              <StatusPill tone="success">Aprovado · v{approved.version}</StatusPill>
              <p>{approved.promise}</p>
              <ul className="space-y-1">
                {(indicators.data ?? []).map((i) => (
                  <li key={i.id} className="flex items-center gap-2 text-muted-foreground">
                    <StatusPill tone="muted">{classLabel[i.classification]}</StatusPill>
                    <span className="text-foreground">{i.name}</span> <Mono>({i.unit})</Mono>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
        <DeteriorationPanel subjectId={s.id} profileId={approved?.id} />
        <Panel title="Histórico de observações" className="lg:col-span-2">
          {observations.isLoading ? (
            <Loading />
          ) : observations.isError ? (
            <ErrorState message="Não foi possível carregar as observações." onRetry={() => observations.refetch()} />
          ) : observations.data!.length === 0 ? (
            <Empty title="Sem observações">Ainda não foram recebidos dados para este cliente.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4 font-normal">Observado</th>
                    <th className="py-2 pr-4 font-normal">Indicador</th>
                    <th className="py-2 pr-4 font-normal">Valor</th>
                    <th className="py-2 pr-4 font-normal">Fonte</th>
                    <th className="py-2 font-normal">Recebido</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {observations.data!.map((o) => (
                    <tr key={o.id}>
                      <td className="py-2 pr-4 whitespace-nowrap">{formatDate(o.observed_at)}</td>
                      <td className="py-2 pr-4"><Mono>{o.indicator_key}</Mono></td>
                      <td className="py-2 pr-4 font-mono tabular-nums">
                        {o.value_numeric ?? o.value_text ?? "—"} <span className="text-muted-foreground">{o.unit}</span>
                        {o.corrects_observation_id && <StatusPill tone="primary">correção</StatusPill>}
                      </td>
                      <td className="py-2 pr-4 text-muted-foreground">{o.source}</td>
                      <td className="py-2 whitespace-nowrap text-muted-foreground">{formatDate(o.ingested_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
      {canWrite && <SubjectDialog open={edit} onOpenChange={setEdit} subject={s} />}
    </>
  );
}
