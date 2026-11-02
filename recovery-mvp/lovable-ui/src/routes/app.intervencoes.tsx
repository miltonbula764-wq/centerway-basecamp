import { LiveOperation } from "@/components/cw/live-operation";
import { Link, createFileRoute } from "@tanstack/react-router";
import { api, customerName } from "@/data/live-runtime";
import { shortId } from "@/data/journey-mapper";
import { pageHead } from "@/lib/seo";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { DecisionBadge, DemoOnly, DemoTag, ListGroupHeader, LockedAction, Notice, PageBar, PropertyPanel, StatusLabel, Tag } from "@/components/cw/primitives";
import type { DecisionStatus } from "@/domain/types";

export const Route = createFileRoute("/app/intervencoes")({
  head: pageHead("Intervenções", "Decisões F04 e execuções sintéticas reversíveis, em modo leitura (demonstração)."),
  validateSearch: (s: Record<string, unknown>): { id?: string } => (typeof s["id"] === "string" ? { id: s["id"] } : {}),
  loader: () => api.listDecisions(),
  component: Intervencoes,
});

const order: DecisionStatus[] = ["blocked", "failed", "executed"];

function Intervencoes() {
  const items = Route.useLoaderData();
  const { id } = Route.useSearch();
  const navigate = Route.useNavigate();
  const sel = items.find((i) => i.id === id);

  return (
    <>
      <PageBar title="Intervenções" count={items.length} />
      <div className="flex flex-col gap-2 px-4 py-3 sm:px-6">
        <Notice tone="warn">Todas as decisões abaixo são sintéticas. Não são intervenções reais e nada é enviado ao cliente.</Notice>
        <p className="text-[12px] text-subtle-foreground">O catálogo e as políticas F04 são provisionados por um administrador e não estão expostos pela API L01; aqui só aparecem decisões registadas e o código de razão.</p>
      </div>
      {order.map((st) => {
        const rows = items.filter((i) => i.status === st);
        if (rows.length === 0) return null;
        return (
          <div key={st}>
            <ListGroupHeader count={rows.length}><DecisionBadge value={st} /></ListGroupHeader>
            {rows.map((i) => (
              <button key={i.id} onClick={() => navigate({ search: { id: i.id } })} className="row-hover flex w-full flex-col gap-1.5 border-b border-border-subtle px-4 py-3 text-left md:min-h-10 md:flex-row md:items-center md:gap-4 md:px-6 md:py-1.5">
                <span className="font-mono text-[11px] text-subtle-foreground md:w-20">{shortId(i.id)}</span>
                <span className="font-mono text-[12px] md:flex-1 md:truncate">{i.reason}</span>
                <span className="text-[12px] text-muted-foreground md:w-44 md:truncate md:text-[13px]"><DemoOnly>{customerName(i.customerId)}</DemoOnly></span>
                {i.reversed && <StatusLabel tone="risk" shape="dash">Revertida</StatusLabel>}
                <span className="flex flex-wrap gap-1.5"><Tag>Ação sintética</Tag><Tag>Não é uma intervenção real</Tag></span>
              </button>
            ))}
          </div>
        );
      })}

      <Sheet open={!!sel} onOpenChange={(o) => !o && navigate({ search: {} })}>
        <SheetContent className="w-full overflow-y-auto border-border-subtle bg-background sm:max-w-md">
          {sel && (
            <div className="flex flex-col gap-6">
              <div>
                <div className="flex flex-wrap gap-1.5"><DemoTag>Ação sintética</DemoTag><DemoTag>Não é uma intervenção real</DemoTag></div>
                <SheetTitle className="page-title mt-3">Decisão F04 {shortId(sel.id)}</SheetTitle>
                <SheetDescription className="mt-1 font-mono text-[11px]">{sel.id} · modo leitura</SheetDescription>
              </div>
              <PropertyPanel
                groups={[{ title: "Decisão", items: [
                  { label: "Estado", value: <DecisionBadge value={sel.status} /> },
                  { label: "Razão (motor)", value: <span className="font-mono text-[12px]">{sel.reason}</span> },
                  { label: "Cliente", value: <Link to="/app/clientes/$id" params={{ id: sel.customerId }} className="hover:text-primary"><DemoOnly>{customerName(sel.customerId)}</DemoOnly></Link> },
                  { label: "Investigação", value: <Link to="/app/investigacoes" search={{ id: sel.investigationId }} className="font-mono text-[12px] hover:text-primary">{shortId(sel.investigationId)}</Link> },
                  { label: "Registada por", value: sel.actor },
                  { label: "Data", value: sel.at.slice(0, 10) },
                ] }]}
              />
              <div>
                <div className="eyebrow mb-2">Execuções sintéticas</div>
                {sel.executions.length === 0 ? <p className="text-muted-foreground">Nenhuma execução.</p> : (
                  <ol className="flex flex-col gap-1.5 border-l border-border-subtle pl-4">
                    {sel.executions.map((e) => <li key={e.id}><span className="font-mono text-[11px] text-subtle-foreground">{shortId(e.id)} · {e.at.slice(0, 10)}</span> {e.isUndo ? "Reversão (undo)" : "Execução"}</li>)}
                  </ol>
                )}
              </div>
              <Notice tone="info">A interface nunca autoriza: a F04 decide com a política provisionada. Uma decisão executada não prova causalidade nem recuperação.</Notice>
              <div className="flex flex-wrap gap-2"><LockedAction>Pedir avaliação F04</LockedAction>{sel.executions.filter((e) => !e.isUndo).map((e) => <LiveOperation key={e.id} client={sel.customerId} operation="undo" arguments={{ execution_id: e.id }} label="Pedir reversão sintética" />)}</div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}

