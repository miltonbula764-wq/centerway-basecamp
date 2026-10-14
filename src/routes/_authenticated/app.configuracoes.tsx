import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { roleLabel, tk, unitLabel, useTenant } from "@/lib/tenant";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, formatDate, Loading, Mono, PageHeader, Panel, StatusPill } from "@/components/app/ui-bits";

export const Route = createFileRoute("/_authenticated/app/configuracoes")({
  head: () => ({
    meta: [
      { title: "Configurações — CENTERWAY" },
      { name: "description", content: "Empresa, membros e registo de auditoria." },
      { property: "og:title", content: "Configurações — CENTERWAY" },
      { property: "og:description", content: "Empresa, membros e registo de auditoria." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Settings,
});

function Settings() {
  const { tenant, user, signOut } = useTenant();
  const members = useQuery({
    queryKey: tk(tenant.id, "members"),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("memberships")
        .select("id, user_id, role, created_at")
        .eq("tenant_id", tenant.id)
        .order("created_at");
      if (error) throw error;
      return data ?? [];
    },
  });
  const audit = useQuery({
    queryKey: tk(tenant.id, "audit"),
    queryFn: async () => {
      const { data, error } = await supabase
        .from("audit_log")
        .select("id, action, entity_type, actor_id, created_at")
        .eq("tenant_id", tenant.id)
        .order("created_at", { ascending: false })
        .limit(30);
      if (error) throw error;
      return data ?? [];
    },
  });

  return (
    <>
      <PageHeader title="Configurações" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Empresa atual">
          <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-sm">
            <dt className="text-muted-foreground">Nome</dt>
            <dd>{tenant.name}</dd>
            <dt className="text-muted-foreground">Tipo de cliente</dt>
            <dd>{unitLabel[tenant.subject_unit_type]}</dd>
            <dt className="text-muted-foreground">O seu papel</dt>
            <dd>{roleLabel[tenant.role]}</dd>
            <dt className="text-muted-foreground">Identificador</dt>
            <dd><Mono className="break-all text-muted-foreground">{tenant.id}</Mono></dd>
          </dl>
        </Panel>
        <Panel title="Sessão">
          <p className="text-sm text-muted-foreground">Sessão iniciada como <span className="text-foreground">{user.email}</span>.</p>
          <Button variant="secondary" className="mt-4" onClick={() => signOut()}>
            <LogOut className="h-4 w-4" /> Terminar sessão
          </Button>
        </Panel>
        <Panel title="Membros" className="lg:col-span-2">
          <p className="mb-3 text-xs text-muted-foreground">
            Convites e alteração de papéis ainda não estão disponíveis nesta interface. Os papéis são aplicados pelo servidor.
          </p>
          {members.isLoading ? (
            <Loading />
          ) : members.isError ? (
            <ErrorState message="Não foi possível carregar os membros." onRetry={() => members.refetch()} />
          ) : (
            <ul className="divide-y divide-border text-sm">
              {members.data!.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center gap-3 py-2">
                  <Mono className="text-muted-foreground">{m.user_id.slice(0, 8)}…</Mono>
                  {m.user_id === user.id && <StatusPill tone="primary">Você</StatusPill>}
                  <span className="ml-auto">{roleLabel[m.role]}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Auditoria (só leitura)" className="lg:col-span-2">
          {audit.isLoading ? (
            <Loading />
          ) : audit.isError ? (
            <ErrorState message="Não foi possível carregar a auditoria." onRetry={() => audit.refetch()} />
          ) : audit.data!.length === 0 ? (
            <Empty title="Sem registos" />
          ) : (
            <ul className="divide-y divide-border text-sm">
              {audit.data!.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-3 py-2">
                  <Mono>{a.action}</Mono>
                  <span className="text-muted-foreground">{a.entity_type}</span>
                  <Mono className="text-muted-foreground">{a.actor_id ? `${a.actor_id.slice(0, 8)}…` : "sistema"}</Mono>
                  <span className="ml-auto text-xs text-muted-foreground">{formatDate(a.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
