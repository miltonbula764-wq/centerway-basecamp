import { Link, createFileRoute } from "@tanstack/react-router";
import { api } from "@/data/live-runtime";
import { shortId } from "@/data/journey-mapper";
import { pageHead } from "@/lib/seo";
import { ActivityFeed, DemoOnly, DemoTag, MetricStrip, Notice, PageBar, PageIntro, PriorityBadge, Section, StatusLabel, stageLabel } from "@/components/cw/primitives";
import { DemoGuide } from "@/components/cw/demo-guide";

export const Route = createFileRoute("/app/")({
  head: pageHead("Visão Geral", "Resumo demonstrativo sobre projeções F06 sintéticas: contratos, orientações, investigações, decisões e recuperações."),
  loader: async () => ({ kpis: await api.getOverviewKpis(), customers: await api.listCustomers(), activities: await api.listActivities() }),
  component: Overview,
});

const rank = { alta: 0, media: 1, baixa: 2 } as const;

function Overview() {
  const { kpis, customers, activities } = Route.useLoaderData();
  const attention = customers.filter((c) => c.workItems.length > 0).sort((a, b) => rank[a.demo?.priority ?? "baixa"] - rank[b.demo?.priority ?? "baixa"]);
  const withGaps = customers.flatMap((c) => c.investigations.filter((i) => i.report && (i.report.contradictions.length || i.report.missing.length)).map((i) => ({ c, i })));

  return (
    <>
      <PageBar title="Visão Geral" />
      <PageIntro title="Visão Geral" description="Contagens calculadas sobre projeções F06 sintéticas dos clientes autorizados nesta sessão de demonstração." />
      <DemoGuide firstCustomerId={attention[0]?.id ?? customers[0]?.id} />
      <div className="flex items-center gap-2 px-4 pb-2 sm:px-6"><DemoTag>Ilustrativo</DemoTag><span className="text-[12px] text-subtle-foreground">Não são métricas reais nem de produção.</span></div>
      <MetricStrip
        items={[
          { label: "Clientes autorizados", value: kpis.clients },
          { label: "Contratos de valor", value: kpis.contracts },
          { label: "Orientações abertas", value: kpis.openWorkItems },
          { label: "Investigações inconclusivas", value: kpis.inconclusiveInvestigations },
          { label: "Decisões F04 executadas / bloqueadas", value: `${kpis.executedDecisions} / ${kpis.blockedDecisions}` },
          { label: "Recuperações avaliadas", value: kpis.evaluatedRecoveries },
        ]}
      />

      <div className="grid lg:grid-cols-[1fr_340px]">
        <div className="min-w-0 lg:border-r lg:border-border-subtle">
          <div className="flex h-10 items-center justify-between px-4 sm:px-6">
            <h3 className="font-medium">Clientes com orientações abertas</h3>
            <Link to="/app/clientes" className="text-[12px] text-muted-foreground hover:text-foreground">Ver todos</Link>
          </div>
          <div className="px-4 pb-2 sm:px-6"><Notice tone="neutral">Orientações F06 descrevem estados guardados e podem estar desatualizadas. Não são permissão, elegibilidade nem causalidade — requerem revalidação.</Notice></div>
          <ul>
            {attention.map((c) => (
              <li key={c.id} className="border-b border-border-subtle">
                <Link to="/app/clientes/$id" params={{ id: c.id }} className="row-hover flex flex-col gap-1 px-4 py-2.5 sm:flex-row sm:items-center sm:gap-4 sm:px-6">
                  <span className="font-medium sm:w-52 sm:truncate"><DemoOnly>{c.displayName}</DemoOnly></span>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">
                    <span className="text-subtle-foreground">{stageLabel[c.workItems[0]!.stage]} · </span>{c.workItems[0]!.label}
                    {c.workItems.length > 1 && <span className="text-subtle-foreground"> · +{c.workItems.length - 1} em paralelo</span>}
                  </span>
                  {c.demo && <DemoOnly><PriorityBadge value={c.demo.priority} /></DemoOnly>}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        <div className="flex flex-col gap-6 px-4 py-4 sm:px-6">
          <Section title="Lacunas e contradições registadas">
            <div className="flex flex-col gap-2">
              {withGaps.map(({ c, i }) => (
                <Notice key={i.id} tone={i.report!.contradictions.length ? "risk" : "warn"}>
                  <Link to="/app/investigacoes" search={{ id: i.id }} className="font-medium text-foreground hover:underline">{c.displayName}</Link>
                  {" — "}
                  {i.report!.contradictions.length} contradição(ões), {i.report!.missing.length} informação(ões) em falta.
                </Notice>
              ))}
            </div>
          </Section>
          <Section title="Recibos recentes">
            <ActivityFeed
              items={activities.slice(0, 6).map((a) => ({
                id: a.requestId,
                when: `${a.at.slice(0, 10)} · ${shortId(a.requestId)}`,
                who: a.customerName,
                text: (
                  <span>
                    {a.operation} · <StatusLabel tone={a.transportStatus === "completed" ? "neutral" : "risk"} shape={a.transportStatus === "completed" ? "ring" : "diamond"}>recibo {a.transportStatus}</StatusLabel>
                    {a.businessStatus && <> · negócio: <span className="font-mono text-[12px]">{a.businessStatus}</span></>}
                  </span>
                ),
              }))}
            />
          </Section>
        </div>
      </div>
    </>
  );
}

