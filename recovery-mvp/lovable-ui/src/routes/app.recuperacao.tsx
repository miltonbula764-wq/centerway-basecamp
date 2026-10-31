import { LiveOperation } from "@/components/cw/live-operation";
import { Link, createFileRoute } from "@tanstack/react-router";
import { Check, CircleHelp, Minus } from "lucide-react";
import { api, customerName } from "@/data/live-runtime";
import { shortId } from "@/data/journey-mapper";
import { pageHead } from "@/lib/seo";
import { DemoOnly, MetricStrip, Notice, PageBar, RecoveryBadge, StatusDot, recoveryLabel, recoveryMeta } from "@/components/cw/primitives";
import type { RecoveryStatus } from "@/domain/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/recuperacao")({
  head: pageHead("Recuperação", "Avaliações F05 antes/depois com janelas comparáveis: completa, parcial, ausência e inconclusivo — sem causalidade."),
  loader: () => api.listRecoveries(),
  component: Recuperacao,
});

function Indicator({ value, label }: { value: boolean | null; label: string }) {
  const Icon = value === null ? CircleHelp : value ? Check : Minus;
  return (
    <li className="flex items-center gap-2">
      <span className={cn("flex size-4 items-center justify-center rounded-full border", value ? "border-ok text-ok" : "border-border text-subtle-foreground")}><Icon className="size-2.5" /></span>
      <span className={value ? "" : "text-muted-foreground"}>{label}<span className="ml-1 text-[11px] text-subtle-foreground">{value === null ? "não determinado" : value ? "sim" : "não"}</span></span>
    </li>
  );
}

function Recuperacao() {
  const recoveries = Route.useLoaderData();
  const order: RecoveryStatus[] = ["recuperacao_completa", "recuperacao_parcial", "ausencia_de_recuperacao", "resultado_inconclusivo"];
  return (
    <>
      <PageBar title="Recuperação" count={recoveries.length} />
      <div className="px-4 py-3 sm:px-6"><Notice tone="info">Recuperação observada não comprova causalidade (causal_attribution = not_established). Resultados são declarados pelo produtor; sem verificação independente.</Notice></div>
      <MetricStrip items={order.map((o) => ({ label: recoveryLabel[o], value: recoveries.filter((r) => r.status === o).length, glyph: <StatusDot tone={recoveryMeta[o][0]} shape={recoveryMeta[o][1]} /> }))} />

      {recoveries.map((r) => {
        const has = r.before !== null && r.after !== null && r.minimum !== null;
        const span = has ? Math.max(r.before!, r.after!, r.minimum!) * 1.15 : 1;
        const pct = (v: number) => `${(v / span) * 100}%`;
        return (
          <article key={r.id} className="grid gap-4 border-b border-border-subtle px-4 py-4 sm:px-6 lg:grid-cols-[1fr_1.3fr_240px] lg:gap-8">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] text-subtle-foreground">{shortId(r.id)}</span>
                <Link to="/app/clientes/$id" params={{ id: r.customerId }} className="text-[12px] text-muted-foreground hover:text-foreground"><DemoOnly>{customerName(r.customerId)}</DemoOnly></Link>
              </div>
              <h3 className="mt-0.5 font-medium">{r.indicator}</h3>
              <div className="mt-1"><RecoveryBadge value={r.status} /></div>
              {r.reason && <p className="mt-1.5 font-mono text-[12px] text-muted-foreground">{r.reason}</p>}
            </div>
            <div>
              <div className="eyebrow mb-2">Antes → depois · revisões {r.windows}{r.asOf ? ` · as_of ${r.asOf.slice(0, 10)}` : ""}</div>
              {has ? (
                <>
                  {([["Antes", r.before!, "bg-neutral"], ["Depois", r.after!, "bg-primary"]] as const).map(([l, v, c]) => (
                    <div key={l} className="mb-2 grid grid-cols-[52px_1fr_64px] items-center gap-3">
                      <span className="text-muted-foreground">{l}</span>
                      <div className="relative h-1.5 rounded-full bg-surface-raised">
                        <div className={`h-1.5 rounded-full ${c}`} style={{ width: pct(v) }} />
                        <div className="absolute -top-1 h-3.5 w-0.5 rounded bg-warn" style={{ left: pct(r.minimum!) }} />
                      </div>
                      <span className="text-right font-mono text-[12px]">{v} {r.unit}</span>
                    </div>
                  ))}
                  <div className="flex items-center gap-1.5 text-[11px] text-subtle-foreground"><span className="h-2.5 w-0.5 rounded bg-warn" />Mínimo aceitável {r.minimum} {r.unit}</div>
                </>
              ) : (
                <p className="text-muted-foreground">Sem valores comparáveis no resultado F05.</p>
              )}
            </div>
            <ul className="flex flex-col justify-center gap-2 lg:border-l lg:border-border-subtle lg:pl-6">
              <Indicator value={r.executionSucceeded} label="Execução bem-sucedida (sintética)" />
              <Indicator value={r.improvementObserved} label="Melhoria observada" />
              <Indicator value={r.minimumMet} label="Mínimo contratual atingido" /><li><LiveOperation client={r.customerId} operation="evaluate_recovery" arguments={{ plan_id: r.id, as_of: new Date().toISOString() }} label="Reavaliar recuperação observada" /></li>
            </ul>
          </article>
        );
      })}
    </>
  );
}

