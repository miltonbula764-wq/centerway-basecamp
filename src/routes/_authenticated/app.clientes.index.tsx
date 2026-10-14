import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { tk, useTenant } from "@/lib/tenant";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Empty, ErrorState, formatDate, Loading, Mono, PageHeader } from "@/components/app/ui-bits";
import { SubjectDialog } from "@/components/app/subject-dialog";

const PAGE = 25;

export const Route = createFileRoute("/_authenticated/app/clientes/")({
  validateSearch: (s: Record<string, unknown>) => ({
    q: typeof s.q === "string" ? s.q : "",
    page: Number(s.page) >= 1 ? Math.floor(Number(s.page)) : 1,
  }),
  head: () => ({
    meta: [
      { title: "Clientes — CENTERWAY" },
      { name: "description", content: "Clientes acompanhados pela empresa." },
      { property: "og:title", content: "Clientes — CENTERWAY" },
      { property: "og:description", content: "Clientes acompanhados pela empresa." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Clientes,
});

function Clientes() {
  const { tenant, canWrite } = useTenant();
  const { q, page } = Route.useSearch();
  const navigate = useNavigate({ from: "/app/clientes/" });
  const [term, setTerm] = useState(q);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      if (term !== q) navigate({ search: { q: term, page: 1 }, replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [term, q, navigate]);

  const list = useQuery({
    queryKey: tk(tenant.id, "subjects", { q, page }),
    placeholderData: keepPreviousData,
    queryFn: async () => {
      let query = supabase
        .from("subjects")
        .select("id, external_ref, display_name, created_at", { count: "exact" })
        .eq("tenant_id", tenant.id)
        .order("created_at", { ascending: false })
        .range((page - 1) * PAGE, page * PAGE - 1);
      const safe = q.replace(/[%,()*\\"]/g, " ").trim().slice(0, 100);
      if (safe) query = query.or(`external_ref.ilike.%${safe}%,display_name.ilike.%${safe}%`);
      const { data, count, error } = await query;
      if (error) throw error;
      return { rows: data ?? [], total: count ?? 0 };
    },
  });

  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <>
      <PageHeader
        title="Clientes"
        description={`${tenant.subject_unit_type === "person" ? "Pessoas" : "Organizações"} acompanhadas. Todos herdam o perfil de valor aprovado da empresa.`}
        actions={
          canWrite && (
            <Button onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> Novo cliente
            </Button>
          )
        }
      />
      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Procurar por referência ou nome" value={term} onChange={(e) => setTerm(e.target.value)} className="pl-9" aria-label="Procurar clientes" />
      </div>

      {list.isLoading ? (
        <Loading />
      ) : list.isError ? (
        <ErrorState message="Não foi possível carregar os clientes." onRetry={() => list.refetch()} />
      ) : list.data!.rows.length === 0 ? (
        <Empty title={q ? "Nenhum cliente encontrado" : "Ainda não há clientes"}>
          {q ? "Experimente outro termo." : canWrite ? "Crie o primeiro cliente com “Novo cliente”." : "Um administrador ou operador pode registar clientes."}
        </Empty>
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <ul className="divide-y divide-border">
              {list.data!.rows.map((s) => (
                <li key={s.id}>
                  <Link
                    to="/app/clientes/$subjectId"
                    params={{ subjectId: s.id }}
                    className="flex flex-col gap-1 px-4 py-3 hover:bg-accent/40 sm:flex-row sm:items-center sm:gap-4"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{s.display_name || <span className="text-muted-foreground">Sem nome</span>}</span>
                    <Mono className="text-muted-foreground">{s.external_ref}</Mono>
                    <span className="text-xs text-muted-foreground sm:w-32 sm:text-right">{formatDate(s.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {total} cliente{total === 1 ? "" : "s"} · página {page} de {pages}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => navigate({ search: { q, page: page - 1 } })} aria-label="Página anterior">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => navigate({ search: { q, page: page + 1 } })} aria-label="Página seguinte">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
      {canWrite && <SubjectDialog open={open} onOpenChange={setOpen} />}
    </>
  );
}
