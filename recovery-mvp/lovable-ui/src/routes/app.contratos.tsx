import { Link, createFileRoute } from "@tanstack/react-router";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { api, customerName } from "@/data/live-runtime";
import { shortId } from "@/data/journey-mapper";
import { pageHead } from "@/lib/seo";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { DemoOnly, LockedAction, PageBar, PropertyPanel, ValueStateBadge } from "@/components/cw/primitives";
import type { ContractVM } from "@/domain/types";

export const Route = createFileRoute("/app/contratos")({
  head: pageHead("Contratos de Valor", "Versões de contratos F01: objetivo, indicador, baseline, mínimo, meta, método, períodos e revisões (demonstração)."),
  validateSearch: (s: Record<string, unknown>): { id?: string } => (typeof s["id"] === "string" ? { id: s["id"] } : {}),
  loader: () => api.listContracts(),
  component: Contratos,
});

const dirLabel = { higher: "Maior é melhor", lower: "Menor é melhor" };
const dirIcon = { higher: ArrowUpRight, lower: ArrowDownRight };

function Ruler({ k }: { k: ContractVM }) {
  const vals = [k.baseline, k.minimum, k.target];
  const lo = Math.min(...vals) * 0.9;
  const hi = Math.max(...vals) * 1.05;
  const pos = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;
  const marks = [{ l: "Baseline", v: k.baseline, c: "bg-neutral" }, { l: "Mínimo", v: k.minimum, c: "bg-warn" }, { l: "Meta", v: k.target, c: "bg-ok" }];
  return (
    <div className="pt-1 pb-7">
      <div className="relative h-1 rounded-full bg-surface-raised">
        {marks.map((m) => (
          <div key={m.l} className="absolute -top-1 flex -translate-x-1/2 flex-col items-center" style={{ left: pos(m.v) }}>
            <span className={`h-3 w-0.5 rounded ${m.c}`} />
            <span className="mt-1 whitespace-nowrap font-mono text-[10px] text-subtle-foreground">{m.l} {m.v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Contratos() {
  const contracts = Route.useLoaderData();
  const { id } = Route.useSearch();
  const navigate = Route.useNavigate();
  const sel = contracts.find((k) => k.id === id);

  return (
    <>
      <PageBar title="Contratos de Valor" count={contracts.length} actions={<LockedAction>Novo contrato</LockedAction>} />
      <div className="hidden h-8 items-center gap-4 border-b border-border-subtle px-6 text-[12px] text-subtle-foreground md:flex">
        <span className="w-24">ID · rev.</span><span className="w-44">Cliente</span><span className="flex-1">Objetivo</span><span className="w-52">Indicador</span><span className="w-48">Última deteção</span>
      </div>
      {contracts.map((k) => {
        const last = k.detections.at(-1);
        return (
          <button key={k.id} onClick={() => navigate({ search: { id: k.id } })} className="row-hover flex w-full flex-col gap-1 border-b border-border-subtle px-4 py-3 text-left md:h-10 md:flex-row md:items-center md:gap-4 md:px-6 md:py-0">
            <span className="font-mono text-[11px] text-subtle-foreground md:w-24">{shortId(k.id)} · r{k.revision}</span>
            <span className="text-[12px] text-muted-foreground md:w-44 md:truncate md:text-[13px]"><DemoOnly>{customerName(k.customerId)}</DemoOnly></span>
            <span className="font-medium md:flex-1 md:truncate">{k.objective}</span>
            <span className="truncate text-muted-foreground md:w-52">{k.indicator}</span>
            <span className="md:w-48">{last ? <ValueStateBadge value={last.state} /> : <span className="text-[12px] text-subtle-foreground">Sem deteção</span>}</span>
          </button>
        );
      })}

      <Sheet open={!!sel} onOpenChange={(o) => !o && navigate({ search: {} })}>
        <SheetContent className="w-full overflow-y-auto border-border-subtle bg-background sm:max-w-md">
          {sel && (() => {
            const Dir = dirIcon[sel.direction];
            return (
              <div className="flex flex-col gap-6">
                <div>
                  <Link to="/app/clientes/$id" params={{ id: sel.customerId }} className="text-[12px] text-muted-foreground hover:text-foreground"><DemoOnly>{customerName(sel.customerId)}</DemoOnly></Link>
                  <SheetTitle className="page-title mt-1">{sel.objective}</SheetTitle>
                  <SheetDescription className="mt-1 font-mono text-[11px]">{sel.id} · revisão {sel.revision} · demonstração</SheetDescription>
                </div>
                <Ruler k={sel} />
                <PropertyPanel
                  groups={[{ title: "Definição (F01)", items: [
                    { label: "Indicador", value: sel.indicator },
                    { label: "Baseline", value: `${sel.baseline} ${sel.unit}` },
                    { label: "Mínimo aceitável", value: `${sel.minimum} ${sel.unit}` },
                    { label: "Meta", value: `${sel.target} ${sel.unit}` },
                    { label: "Direção", value: <span className="inline-flex items-center gap-1"><Dir className="size-3.5" />{dirLabel[sel.direction]}</span> },
                    { label: "Método", value: sel.method },
                    { label: "Período baseline", value: <span className="font-mono text-[12px]">{sel.baselinePeriod}</span> },
                    { label: "Período", value: <span className="font-mono text-[12px]">{sel.period}</span> },
                    { label: "Fonte", value: sel.sourceName },
                  ] }]}
                />
                <div>
                  <div className="eyebrow mb-2">Deteções F02</div>
                  {sel.detections.length === 0 ? <p className="text-muted-foreground">Nenhuma. A orientação F06 indica fornecer revisões, corte e política de períodos.</p> : (
                    <ul className="flex flex-col gap-1.5">{sel.detections.map((d) => <li key={d.id} className="flex flex-wrap items-center gap-2"><span className="font-mono text-[11px] text-subtle-foreground">{shortId(d.id)} · r{d.revision} · {d.asOf.slice(0, 10)}</span><ValueStateBadge value={d.state} /></li>)}</ul>
                  )}
                </div>
                <div>
                  <div className="eyebrow mb-2">Revisões</div>
                  <ol className="flex flex-col gap-2 border-l border-border-subtle pl-4">
                    {sel.revisions.map((r) => <li key={r.revision}><span className="font-mono text-[11px] text-subtle-foreground">r{r.revision} · {r.at.slice(0, 10)} · {r.actor}</span><div>{r.reason}</div></li>)}
                  </ol>
                </div>
                <LockedAction>Nova revisão (append_value)</LockedAction>
              </div>
            );
          })()}
        </SheetContent>
      </Sheet>
    </>
  );
}

