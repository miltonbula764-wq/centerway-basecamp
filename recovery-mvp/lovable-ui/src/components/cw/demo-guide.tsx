import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowRight, X } from "lucide-react";
import { DemoTag } from "./primitives";

/** Plain-language concepts shown to first-time visitors. No numbers, no causality claims. */
export const demoConcepts = [
  {
    term: "Valor prometido",
    text: "O objetivo que a empresa combinou com o cliente e como vai ser medido.",
  },
  {
    term: "Deterioração",
    text: "Sinais de que esse valor está a cair ou de que algo impede o cliente de o obter.",
  },
  {
    term: "Recuperação observada",
    text: "Comparação entre medições antes e depois. Mostra se houve melhoria, mas não prova o que a causou.",
  },
] as const;

export const demoCompanyLabel = "Empresa de demonstração";
export const demoProvenance = "DEMONSTRAÇÃO — dados sintéticos";

/** Discreet "how to explore" block. Dismissal lives only in memory (returns on reload). */
export function DemoGuide({ firstCustomerId }: { firstCustomerId?: string | undefined }) {
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;
  return (
    <section
      aria-labelledby="demo-guide-title"
      className="mx-4 mb-3 rounded-md border border-border-subtle bg-surface px-4 py-3 sm:mx-6"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <DemoTag>{demoProvenance}</DemoTag>
          <h2 id="demo-guide-title" className="text-[13px] font-medium">
            Como explorar esta demonstração
          </h2>
        </div>
        <button
          type="button"
          onClick={() => setHidden(true)}
          aria-label="Ocultar guia"
          className="flex size-7 shrink-0 items-center justify-center rounded-md text-subtle-foreground hover:bg-surface-hover hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring max-sm:size-11"
        >
          <X className="size-3.5" />
        </button>
      </div>
      <p className="mt-1.5 text-[13px] text-muted-foreground">
        O CENTERWAY ajuda uma empresa SaaS a acompanhar se os seus clientes estão a receber o valor
        prometido. Aqui vê a {demoCompanyLabel.toLowerCase()}, com clientes fictícios. Os registos vêm da API pública. Intervenções só são enviadas após confirmação e autorização do servidor.
      </p>
      <dl className="mt-3 grid gap-3 sm:grid-cols-3">
        {demoConcepts.map((c) => (
          <div key={c.term}>
            <dt className="text-[12px] font-medium text-foreground">{c.term}</dt>
            <dd className="text-[12px] text-muted-foreground">{c.text}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 flex flex-wrap gap-2">
        <Link
          to="/app/clientes"
          className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-[13px] font-medium text-primary-foreground hover:bg-primary/90 max-sm:h-11"
        >
          Ver clientes de demonstração <ArrowRight className="size-3.5" />
        </Link>
        {firstCustomerId && (
          <Link
            to="/app/clientes/$id"
            params={{ id: firstCustomerId }}
            className="inline-flex h-8 items-center rounded-md border border-border-subtle px-3 text-[13px] text-foreground hover:bg-surface-hover max-sm:h-11"
          >
            Abrir um caso de exemplo
          </Link>
        )}
      </div>
    </section>
  );
}

