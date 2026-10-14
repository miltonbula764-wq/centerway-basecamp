import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Circle } from "lucide-react";
import { useTenant, unitLabel, roleLabel } from "@/lib/tenant";
import { countQuery, indicatorsQuery, profilesQuery } from "@/lib/queries";
import { ErrorState, Loading, PageHeader, Panel, StatusPill } from "@/components/app/ui-bits";
import { statusLabel } from "@/lib/profile";

export const Route = createFileRoute("/_authenticated/app/")({
  head: () => ({
    meta: [
      { title: "Visão geral — CENTERWAY" },
      { name: "description", content: "Estado da configuração e contagens reais da empresa." },
      { property: "og:title", content: "Visão geral — CENTERWAY" },
      { property: "og:description", content: "Estado da configuração e contagens reais da empresa." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Overview,
});

function Overview() {
  const { tenant } = useTenant();
  const subjects = useQuery(countQuery(tenant.id, "subjects"));
  const obs = useQuery(countQuery(tenant.id, "observations"));
  const batches = useQuery(countQuery(tenant.id, "ingestion_batches"));
  const members = useQuery(countQuery(tenant.id, "memberships"));
  const profiles = useQuery(profilesQuery(tenant.id));
  const approved = profiles.data?.find((p) => p.status === "approved");
  const draft = profiles.data?.find((p) => p.status === "draft");
  const draftInd = useQuery({ ...indicatorsQuery(tenant.id, draft?.id ?? ""), enabled: !!draft });

  const anyError = [subjects, obs, batches, members, profiles].find((q) => q.isError);
  const loading = [subjects, obs, batches, members, profiles].some((q) => q.isLoading);

  const hasOutcomeDraft = (draftInd.data ?? []).some((i) => i.classification === "outcome");
  const steps = [
    { done: !!draft || !!approved, label: "Definir a promessa de valor (rascunho do perfil)", to: "/app/perfil" as const },
    { done: !!approved || hasOutcomeDraft, label: "Adicionar pelo menos um indicador de resultado", to: "/app/perfil" as const },
    { done: !!approved, label: "Aprovar o perfil de valor (administrador)", to: "/app/perfil" as const },
    { done: (subjects.data ?? 0) > 0, label: "Registar clientes acompanhados", to: "/app/clientes" as const },
    { done: (obs.data ?? 0) > 0, label: "Importar observações — disponível numa próxima etapa", to: "/app/dados" as const },
  ];

  return (
    <>
      <PageHeader title="Visão geral" description={`${tenant.name} · ${unitLabel[tenant.subject_unit_type]} · ${roleLabel[tenant.role]}`} />
      {anyError ? (
        <ErrorState message="Não foi possível carregar as contagens." onRetry={() => anyError.refetch()} />
      ) : loading ? (
        <Loading />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Clientes" value={subjects.data!} />
            <Stat label="Observações" value={obs.data!} />
            <Stat label="Lotes de dados" value={batches.data!} />
            <Stat label="Membros" value={members.data!} />
          </div>
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <Panel title="Próximos passos de configuração">
              <ol className="space-y-1">
                {steps.map((s) => (
                  <li key={s.label}>
                    <Link to={s.to} className="flex items-center gap-3 rounded-md px-2 py-2 text-sm hover:bg-accent/50">
                      {s.done ? <CheckCircle2 className="h-4 w-4 text-success" /> : <Circle className="h-4 w-4 text-muted-foreground" />}
                      <span className={s.done ? "text-muted-foreground line-through" : ""}>{s.label}</span>
                      <ArrowRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
                    </Link>
                  </li>
                ))}
              </ol>
            </Panel>
            <Panel title="Perfil de valor">
              {approved ? (
                <div className="space-y-2 text-sm">
                  <StatusPill tone="success">{statusLabel.approved} · v{approved.version}</StatusPill>
                  <p className="line-clamp-4 text-muted-foreground">{approved.promise}</p>
                </div>
              ) : draft ? (
                <div className="space-y-2 text-sm">
                  <StatusPill tone="primary">{statusLabel.draft} · v{draft.version}</StatusPill>
                  <p className="text-muted-foreground">Ainda não há perfil aprovado. Os clientes não têm um perfil herdado.</p>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Ainda não existe perfil de valor.</p>
              )}
            </Panel>
          </div>
          <Panel title="Casos">
            <p className="text-sm text-muted-foreground">
              A deteção de deterioração já pode ser corrida na página de cada cliente e produz apenas sinais candidatos. A abertura de casos chega numa próxima etapa.
            </p>
          </Panel>
        </div>
      )}
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-2xl tabular-nums">{value.toLocaleString("pt-PT")}</p>
    </div>
  );
}
