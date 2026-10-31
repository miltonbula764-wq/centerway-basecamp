import { Link, createFileRoute, notFound } from "@tanstack/react-router";
import { ChevronDown, ChevronUp } from "lucide-react";
import { api } from "@/data/live-runtime";
import { shortId } from "@/data/journey-mapper";
import { pageHead } from "@/lib/seo";
import { cn } from "@/lib/utils";
import {
  DecisionBadge,
  DemoOnly,
  EmptyState,
  InvestigationBadge,
  LockedAction,
  Notice,
  PageBar,
  PriorityBadge,
  PropertyPanel,
  RecoveryBadge,
  Section,
  StatusDot,
  StatusLabel,
  ValueStateBadge,
  stageLabel,
} from "@/components/cw/primitives";
import { ErrorState } from "@/components/cw/states";

async function loadCustomer(id: string) {
  const all = await api.listCustomers();
  const index = all.findIndex((c) => c.id === id);
  const customer = all[index];
  if (!customer) throw notFound();
  return { customer, position: { index, total: all.length, prev: all[index - 1]?.id, next: all[index + 1]?.id } };
}

export const Route = createFileRoute("/app/clientes/$id")({
  head: pageHead("Detalhe do cliente", "Percurso F06 demonstrativo do cliente: contratos e casos em paralelo, orientações, recibos e fontes."),
  loader: ({ params }) => loadCustomer(params.id),
  notFoundComponent: () => <ErrorState kind="404" action={<Link to="/app/clientes" className="text-primary">Voltar a Clientes</Link>} />,
  component: Detalhe,
});

function NavArrow({ id, dir }: { id?: string | undefined; dir: "prev" | "next" }) {
  const Icon = dir === "prev" ? ChevronUp : ChevronDown;
  const cls = "flex size-7 items-center justify-center rounded-md border max-sm:size-11";
  if (!id) return <span aria-disabled className={cn(cls, "opacity-40")}><Icon className="size-3.5" /></span>;
  return <Link to="/app/clientes/$id" params={{ id }} aria-label={dir === "prev" ? "Cliente anterior" : "Cliente seguinte"} className={cn(cls, "hover:bg-surface-hover")}><Icon className="size-3.5" /></Link>;
}

const tlTone = { contract: "info", detection: "warn", investigation: "info", decision: "neutral", execution: "ok", undo: "risk", recovery: "ok" } as const;

function Row({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-9 flex-wrap items-center gap-x-4 gap-y-1 border-b border-border-subtle py-2">{children}</div>;
}
const Mono = ({ children }: { children: React.ReactNode }) => <span className="font-mono text-[11px] text-subtle-foreground">{children}</span>;

function Detalhe() {
  const { customer: c, position } = Route.useLoaderData();
  return (
    <>
      <PageBar
        crumbs={[{ label: "Clientes", to: "/app/clientes" }]}
        title={c.displayName}
        actions={<><Mono>{position.index + 1} / {position.total}</Mono><NavArrow id={position.prev} dir="prev" /><NavArrow id={position.next} dir="next" /></>}
      />
      <div className="grid lg:grid-cols-[1fr_300px]">
        <div className="min-w-0 px-4 py-6 sm:px-8 lg:border-r lg:border-border-subtle">
          <Mono>{c.id}</Mono>
          <h2 className="page-title mt-1"><DemoOnly>{c.displayName}</DemoOnly></h2>
          <p className="mt-1 text-muted-foreground">{c.contracts.length} contrato(s) · {c.investigations.length} investigação(ões) · {c.workItems.length} orientação(ões) em paralelo</p>
          <div className="mt-3"><LockedAction>Registar valor (append_value)</LockedAction></div>

          <Section title="Orientações F06 (work_items)" className="mt-8" flush>
            <div className="py-2"><Notice tone="neutral">Orientação sobre estados guardados. Pode estar desatualizada; não é permissão, elegibilidade nem causalidade. A F04 revalida sempre antes de executar.</Notice></div>
            {c.workItems.length === 0 ? <EmptyState>Sem orientações abertas.</EmptyState> : c.workItems.map((w, i) => (
              <Row key={i}>
                <span className="w-24 text-[12px] text-subtle-foreground">{stageLabel[w.stage]}</span>
                <span className="flex-1">{w.label}</span>
                {w.refId && <Mono>{shortId(w.refId)}</Mono>}
                {w.asOf && <Mono>as_of {w.asOf.slice(0, 10)}</Mono>}
                {w.notes.length > 0 && <ul className="w-full text-[12px] sm:pl-28 text-muted-foreground">{w.notes.map((n) => <li key={n}>· {n}</li>)}</ul>}
              </Row>
            ))}
          </Section>

          <Section title="Contratos de valor" className="mt-6" flush aside={<Link to="/app/contratos" className="text-[12px] text-muted-foreground hover:text-foreground">Abrir</Link>}>
            {c.contracts.length === 0 ? <EmptyState>Sem contrato explícito registado.</EmptyState> : c.contracts.map((k) => (
              <Row key={k.id}>
                <Mono>{shortId(k.id)} · r{k.revision}</Mono>
                <span className="flex-1">{k.objective}</span>
                {k.detections.length === 0 ? <span className="text-[12px] text-subtle-foreground">Sem deteção</span> : <ValueStateBadge value={k.detections.at(-1)!.state} />}
              </Row>
            ))}
          </Section>

          <Section title="Investigações" className="mt-6" flush>
            {c.investigations.length === 0 ? <EmptyState>Sem investigações.</EmptyState> : c.investigations.map((i) => (
              <Link key={i.id} to="/app/investigacoes" search={{ id: i.id }} className="row-hover -mx-2 block rounded px-2">
                <Row><Mono>{shortId(i.id)}</Mono><span className="flex-1">{i.question}</span><InvestigationBadge value={i.report?.status ?? null} /></Row>
              </Link>
            ))}
          </Section>

          <Section title="Decisões e recuperação" className="mt-6" flush>
            {c.decisions.length === 0 ? <EmptyState>Sem decisões F04.</EmptyState> : c.decisions.map((d) => (
              <Link key={d.id} to="/app/intervencoes" search={{ id: d.id }} className="row-hover -mx-2 block rounded px-2">
                <Row><Mono>{shortId(d.id)}</Mono><span className="flex-1 font-mono text-[12px]">{d.reason}</span>{d.reversed && <StatusLabel tone="risk" shape="dash">Revertida</StatusLabel>}<DecisionBadge value={d.status} /></Row>
              </Link>
            ))}
            {c.recoveries.map((r) => (
              <Row key={r.id}><Mono>{shortId(r.id)}</Mono><span className="flex-1 text-muted-foreground">{r.indicator} · {r.windows}</span><RecoveryBadge value={r.status} /></Row>
            ))}
            {c.recoveries.length > 0 && <div className="mt-3"><Notice tone="info">Recuperação observada não comprova causalidade.</Notice></div>}
          </Section>

          <Section title="Linha temporal" className="mt-6">
            <ol className="relative ml-1 border-l border-border-subtle">
              {c.timeline.map((t) => (
                <li key={t.refId + t.at} className="relative pb-3 pl-5 last:pb-0">
                  <span className="absolute top-[5px] -left-[5px] flex size-[9px] items-center justify-center bg-background"><StatusDot tone={tlTone[t.kind]} shape={t.kind === "undo" ? "diamond" : "dot"} /></span>
                  <div className="flex flex-wrap items-baseline gap-x-2"><span>{t.label}</span><Mono>{t.at.slice(0, 10)}</Mono></div>
                </li>
              ))}
            </ol>
          </Section>

          <Section title="Recibos de operações" className="mt-6" flush>
            {c.receipts.length === 0 ? <EmptyState>Sem recibos.</EmptyState> : c.receipts.map((r) => (
              <Row key={r.requestId}>
                <Mono>{shortId(r.requestId)}</Mono>
                <span className="w-36 font-mono text-[12px]">{r.operation}</span>
                <StatusLabel tone={r.transportStatus === "completed" ? "neutral" : "risk"} shape={r.transportStatus === "completed" ? "ring" : "diamond"}>recibo {r.transportStatus}</StatusLabel>
                <span className="flex-1 text-[12px] text-muted-foreground">negócio: <span className="font-mono">{r.businessStatus ?? "—"}</span></span>
                <Mono>{r.actor} · {r.at.slice(0, 10)}</Mono>
              </Row>
            ))}
          </Section>
        </div>

        <div className="border-t border-border-subtle px-4 py-6 sm:px-6 lg:border-t-0">
          <PropertyPanel
            groups={[
              { title: "Identificação (API)", items: [
                { label: "Tenant", value: <Mono>{shortId(c.tenantId)}</Mono> },
                { label: "Cliente", value: <Mono>{shortId(c.id)}</Mono> },
              ] },
              { title: "Só demonstração (sem fonte HTTP)", items: c.demo ? [
                { label: "Nome", value: <DemoOnly>{c.demo.company}</DemoOnly> },
                { label: "Segmento", value: <DemoOnly>{c.demo.segment}</DemoOnly> },
                { label: "Plano", value: <DemoOnly>{c.demo.plan}</DemoOnly> },
                { label: "Responsável", value: <DemoOnly>{c.demo.owner}</DemoOnly> },
                { label: "Prioridade", value: <DemoOnly><PriorityBadge value={c.demo.priority} /></DemoOnly> },
              ] : [{ label: "Metadados", value: "—" }] },
              { title: "Fontes (F01)", items: c.sources.length === 0
                ? [{ label: "Fontes", value: <span className="text-muted-foreground">Nenhuma registada</span> }]
                : c.sources.map((s) => ({ label: s.name, value: <span className="flex flex-col"><span className="text-muted-foreground">{s.method}</span><Mono>r{s.revision} · {s.recordedAt.slice(0, 10)}</Mono></span> })) },
            ]}
          />
          <p className="mt-4 text-[12px] text-subtle-foreground">A projeção não indica cobertura ou qualidade agregada de fontes; a qualidade é declarada por evidência.</p>
        </div>
      </div>
    </>
  );
}

