import { LiveOperation } from "@/components/cw/live-operation";
import { Link, createFileRoute } from "@tanstack/react-router";
import { ChevronLeft } from "lucide-react";
import { api, customerName } from "@/data/live-runtime";
import { shortId } from "@/data/journey-mapper";
import { pageHead } from "@/lib/seo";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DemoOnly, EvidenceBlock, InvestigationBadge, LockedAction, Notice, PageBar, ValueStateBadge } from "@/components/cw/primitives";
import { NoDataState } from "@/components/cw/states";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/investigacoes")({
  head: pageHead("Investigações", "Investigações F03: factos, hipóteses, contradições e informação em falta, sem inferência causal (demonstração)."),
  validateSearch: (s: Record<string, unknown>): { id?: string } => (typeof s["id"] === "string" ? { id: s["id"] } : {}),
  loader: () => api.listInvestigations(),
  component: Investigacoes,
});

function Investigacoes() {
  const investigations = Route.useLoaderData();
  const { id } = Route.useSearch();
  const explicit = investigations.find((i) => i.id === id);
  const inv = explicit ?? investigations[0];
  if (!inv) return <><PageBar title="Investigações" count={0} /><NoDataState>Sem investigações.</NoDataState></>;
  const r = inv.report;

  return (
    <>
      <PageBar title="Investigações" count={investigations.length} />
      <div className="grid lg:grid-cols-[300px_1fr]">
        <ul className={cn("border-border-subtle lg:border-r", explicit && "max-lg:hidden")}>
          {investigations.map((i) => (
            <li key={i.id}>
              <Link to="/app/investigacoes" search={{ id: i.id }} aria-current={i.id === inv.id ? "true" : undefined} className={cn("row-hover block border-b border-border-subtle px-4 py-2.5 sm:px-6 lg:px-4", i.id === inv.id && "lg:bg-surface-raised")}>
                <div className="flex items-center justify-between gap-2"><span className="font-mono text-[11px] text-subtle-foreground">{shortId(i.id)}</span><InvestigationBadge value={i.report?.status ?? null} /></div>
                <div className="mt-0.5 font-medium">{i.question}</div>
                <div className="text-[12px] text-muted-foreground">{customerName(i.customerId)}</div>
              </Link>
            </li>
          ))}
        </ul>

        <div className={cn("min-w-0 px-4 py-6 sm:px-8", !explicit && "max-lg:hidden")}>
          <Link to="/app/investigacoes" className="mb-3 inline-flex h-11 items-center gap-1 text-muted-foreground lg:hidden"><ChevronLeft className="size-4" /> Investigações</Link>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-mono text-[11px] text-subtle-foreground">{inv.id}</span>
            <Link to="/app/clientes/$id" params={{ id: inv.customerId }} className="text-[12px] text-muted-foreground hover:text-foreground"><DemoOnly>{customerName(inv.customerId)}</DemoOnly></Link>
            <span className="font-mono text-[11px] text-subtle-foreground">aberta {inv.openedAt.slice(0, 10)} · {inv.actor}</span>
            <InvestigationBadge value={r?.status ?? null} />
          </div>
          <h2 className="page-title mt-2">{inv.question}</h2>

          <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-border-subtle bg-surface px-3 py-2 text-[12px]">
            <span className="eyebrow">Deteção associada</span>
            <span className="font-mono">{shortId(inv.detectionId)}</span>
            {inv.detectionState && <ValueStateBadge value={inv.detectionState} />}
            <span className="font-mono text-subtle-foreground">contrato {shortId(inv.contractId)} · r{inv.contractRevision}</span>
          </div>

          {r === null ? (
            <div className="mt-4"><Notice tone="neutral">Sem avaliação persistida. A orientação F06 é avaliar fatores e evidências registados (investigate).</Notice></div>
          ) : (
            <div className="mt-4">
              <EvidenceBlock kind="facts" items={r.facts} />
              <EvidenceBlock kind="hypotheses" items={r.hypotheses} />
              <EvidenceBlock kind="contradictions" items={r.contradictions} />
              <EvidenceBlock kind="missing" items={r.missing} />
            </div>
          )}

          <Tabs defaultValue="candidatos" className="mt-6" key={inv.id}>
            <TabsList className="h-8 bg-surface">
              <TabsTrigger value="candidatos" className="text-[12px]">Candidatos</TabsTrigger>
              <TabsTrigger value="referencias" className="text-[12px]">Referências</TabsTrigger>
              <TabsTrigger value="versoes" className="text-[12px]">Versões</TabsTrigger>
            </TabsList>
            <TabsContent value="candidatos" className="mt-3 flex flex-col gap-2">
              <Notice tone="info">Candidatos de intervenção não equivalem a causalidade provada nem a autorização. A F03 regista causal_inference = not_performed; a F04 decide com políticas provisionadas.</Notice>
              {(r?.candidates ?? []).length === 0 ? <p className="text-muted-foreground">Sem candidatos.</p> : r!.candidates.map((cnd) => (
                <div key={cnd} className="flex min-h-9 items-center rounded-md border border-border-subtle px-3">{cnd}</div>
              ))}
              {inv.decisionIds.map((d) => <Link key={d} to="/app/intervencoes" search={{ id: d }} className="text-[12px] text-primary">Decisão F04 {shortId(d)}</Link>)}
              <div className="flex flex-wrap gap-2"><LiveOperation client={inv.customerId} operation="investigate" arguments={{ investigation_id: inv.id, as_of: new Date().toISOString() }} label="Reavaliar investigação" />{r && <LiveOperation client={inv.customerId} operation="intervene" arguments={{ investigation_id: inv.id, report_id: r.reportId }} label="Pedir intervenção sintética autorizada" />}</div>
            </TabsContent>
            <TabsContent value="referencias" className="mt-3">
              <ul className="flex flex-col gap-1 font-mono text-[12px]">
                <li>detection_id {inv.detectionId}</li>
                <li>contract_id {inv.contractId} · r{inv.contractRevision}</li>
                {r && <li>report_id {r.reportId}</li>}
              </ul>
            </TabsContent>
            <TabsContent value="versoes" className="mt-3 flex flex-col gap-2">
              {r ? <p><span className="font-mono text-[11px] text-subtle-foreground">as_of {r.asOf.slice(0, 10)}</span> · última avaliação persistida</p> : <p className="text-muted-foreground">Nenhuma avaliação persistida.</p>}
              <p className="text-[12px] text-subtle-foreground">A projeção F06 só inclui a última avaliação. O histórico de runs existe nas portas do motor, não expostas pela API L01.</p>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </>
  );
}

