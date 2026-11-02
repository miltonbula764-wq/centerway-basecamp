import { useMemo, useState } from "react";
import { Link, createFileRoute } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { api } from "@/data/live-runtime";
import { shortId } from "@/data/journey-mapper";
import { pageHead } from "@/lib/seo";
import { DemoOnly, EmptyState, FilterChips, PageBar, PriorityBadge, stageLabel } from "@/components/cw/primitives";
import type { Stage } from "@/domain/types";
import { demoCompanyLabel, demoProvenance } from "@/components/cw/demo-guide";

export const Route = createFileRoute("/app/clientes/")({
  head: pageHead("Clientes", "Clientes autorizados na sessão de demonstração, com contratos e orientações F06 em paralelo."),
  loader: () => api.listCustomers(),
  component: Clientes,
});

const stages: Stage[] = ["contract", "detection", "investigation", "intervention", "recovery"];

function Clientes() {
  const customers = Route.useLoaderData();
  const [q, setQ] = useState("");
  const [f, setF] = useState<Stage | "todos">("todos");
  const has = (c: (typeof customers)[number], s: Stage) => c.workItems.some((w) => w.stage === s);
  const list = useMemo(
    () => customers.filter((c) => (f === "todos" || has(c, f)) && (c.displayName + c.id + c.contracts.map((k) => k.objective).join(" ")).toLowerCase().includes(q.toLowerCase())),
    [customers, q, f],
  );

  return (
    <>
      <PageBar title="Clientes" count={list.length} />
      <div className="flex flex-col gap-2 border-b border-border-subtle px-4 py-2 sm:flex-row sm:items-center sm:px-6">
        <label className="relative flex items-center sm:w-72">
          <span className="sr-only">Pesquisar</span>
          <Search className="pointer-events-none absolute left-2.5 size-3.5 text-subtle-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar cliente, ID ou objetivo" className="h-8 w-full rounded-md border border-input bg-surface pr-2 pl-8 text-[13px] placeholder:text-subtle-foreground focus:outline-none focus-visible:border-ring max-sm:h-11" />
        </label>
        <FilterChips
          value={f}
          onChange={setF}
          options={[{ value: "todos" as const, label: "Todos", count: customers.length }, ...stages.map((s) => ({ value: s, label: stageLabel[s], count: customers.filter((c) => has(c, s)).length }))]}
        />
      </div>
      <p className="border-b border-border-subtle px-4 py-2 text-[12px] text-subtle-foreground sm:px-6">
        <span className="font-medium text-muted-foreground">{demoCompanyLabel}</span> · {demoProvenance}. Escolha um cliente para ver contratos, deteções, investigações, intervenções sintéticas autorizadas e recuperação. A API devolve apenas clientes autorizados. Os nomes vêm do diretório; plano, segmento, responsável e prioridade não são inventados.
      </p>

      {list.length === 0 ? (
        <EmptyState>Nenhum cliente corresponde aos filtros.</EmptyState>
      ) : (
        <div role="table" aria-label="Clientes">
          <div role="row" className="hidden h-8 items-center gap-4 border-b border-border-subtle px-6 text-[12px] text-subtle-foreground md:flex">
            <span role="columnheader" className="w-20">ID</span>
            <span role="columnheader" className="w-56">Cliente</span>
            <span role="columnheader" className="w-20">Contratos</span>
            <span role="columnheader" className="flex-1">Orientações F06</span>
            <span role="columnheader" className="w-32">Prioridade</span>
          </div>
          {list.map((c) => (
            <Link key={c.id} role="row" to="/app/clientes/$id" params={{ id: c.id }} className="row-hover flex flex-col gap-1 border-b border-border-subtle px-4 py-3 md:h-10 md:flex-row md:items-center md:gap-4 md:px-6 md:py-0">
              <span className="font-mono text-[11px] text-subtle-foreground md:w-20">{shortId(c.id)}</span>
              <span className="truncate font-medium md:w-56"><DemoOnly>{c.displayName}</DemoOnly></span>
              <span className="text-muted-foreground md:w-20"><span className="md:hidden">Contratos: </span>{c.contracts.length}</span>
              <span className="min-w-0 truncate text-muted-foreground md:flex-1">
                {c.workItems.length === 0 ? "Sem orientações abertas" : `${c.workItems.length} · ${c.workItems.map((w) => stageLabel[w.stage]).join(", ")}`}
              </span>
              <span className="md:w-32">{c.demo && <DemoOnly><PriorityBadge value={c.demo.priority} /></DemoOnly>}</span>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

