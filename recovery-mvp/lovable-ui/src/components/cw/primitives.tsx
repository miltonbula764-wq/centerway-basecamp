import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { ChevronRight, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { DecisionStatus, InvestigationStatus, Priority, RecoveryStatus, Stage, ValueState } from "@/domain/types";

export type Tone = "ok" | "warn" | "risk" | "info" | "neutral";
export type Shape = "dot" | "ring" | "diamond" | "dash" | "half";

const toneText: Record<Tone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  risk: "text-risk",
  info: "text-info",
  neutral: "text-neutral",
};

/** Shape-coded status glyph: meaning never relies on colour alone. */
export function StatusDot({ tone = "neutral", shape = "dot", className }: { tone?: Tone | undefined; shape?: Shape | undefined; className?: string }) {
  const c = cn("inline-block shrink-0", toneText[tone], className);
  if (shape === "diamond") return <span aria-hidden className={cn(c, "size-2 rotate-45 bg-current")} />;
  if (shape === "ring") return <span aria-hidden className={cn(c, "size-2.5 rounded-full border-[1.5px] border-current")} />;
  if (shape === "dash") return <span aria-hidden className={cn(c, "size-2.5 rounded-full border-[1.5px] border-dashed border-current")} />;
  if (shape === "half")
    return (
      <span aria-hidden className={cn(c, "relative size-2.5 overflow-hidden rounded-full border-[1.5px] border-current")}>
        <span className="absolute inset-y-0 left-0 w-1/2 bg-current" />
      </span>
    );
  return <span aria-hidden className={cn(c, "size-2 rounded-full bg-current")} />;
}

export function StatusLabel({ tone, shape, children, className }: { tone?: Tone | undefined; shape?: Shape | undefined; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-[13px] text-muted-foreground", className)}>
      <StatusDot tone={tone} shape={shape} />
      {children}
    </span>
  );
}

export function Tag({ children, tone, className }: { children: ReactNode; tone?: Tone; className?: string }) {
  return (
    <span className={cn("inline-flex h-5 items-center gap-1.5 whitespace-nowrap rounded-full border px-2 text-[11px] text-muted-foreground", className)}>
      {tone && <StatusDot tone={tone} className="size-1.5" />}
      {children}
    </span>
  );
}

const prioMap: Record<Priority, [Tone, string, number]> = { alta: ["risk", "Alta", 3], media: ["warn", "Média", 2], baixa: ["neutral", "Baixa", 1] };
export function PriorityBadge({ value }: { value: Priority }) {
  const [tone, label, n] = prioMap[value];
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] text-muted-foreground">
      <span aria-hidden className="flex h-3 items-end gap-[2px]">
        {[1, 2, 3].map((i) => (
          <span key={i} className={cn("w-[3px] rounded-sm", i <= n ? cn("bg-current", toneText[tone]) : "bg-border")} style={{ height: `${4 + i * 3}px` }} />
        ))}
      </span>
      {label}
    </span>
  );
}

const valueStateMap: Record<ValueState, [Tone, Shape, string]> = {
  valor_demonstrado: ["ok", "dot", "Valor demonstrado"],
  deterioracao_demonstrada: ["risk", "diamond", "Deterioração demonstrada"],
  valor_insuficiente: ["warn", "half", "Valor insuficiente"],
  resultado_inconclusivo: ["neutral", "dash", "Resultado inconclusivo"],
};
export const ValueStateBadge = ({ value }: { value: ValueState }) => <StatusLabel tone={valueStateMap[value][0]} shape={valueStateMap[value][1]}>{valueStateMap[value][2]}</StatusLabel>;

const invMap: Record<InvestigationStatus, [Tone, Shape, string]> = {
  impedimento_demonstrado: ["info", "dot", "Impedimento demonstrado"],
  nenhum_impedimento_demonstrado: ["neutral", "ring", "Nenhum impedimento demonstrado"],
  inconclusivo: ["warn", "dash", "Inconclusivo"],
};
export const InvestigationBadge = ({ value }: { value: InvestigationStatus | null }) =>
  value === null ? <StatusLabel tone="neutral" shape="ring">Sem avaliação persistida</StatusLabel> : <StatusLabel tone={invMap[value][0]} shape={invMap[value][1]}>{invMap[value][2]}</StatusLabel>;

export const decisionLabel: Record<DecisionStatus, string> = { blocked: "Bloqueada (F04)", executed: "Executada (sintética)", failed: "Falhada" };
const decMap: Record<DecisionStatus, [Tone, Shape]> = { blocked: ["risk", "diamond"], executed: ["ok", "dot"], failed: ["warn", "half"] };
export const DecisionBadge = ({ value }: { value: DecisionStatus }) => <StatusLabel tone={decMap[value][0]} shape={decMap[value][1]}>{decisionLabel[value]}</StatusLabel>;

export const recoveryLabel: Record<RecoveryStatus, string> = {
  recuperacao_completa: "Recuperação completa",
  recuperacao_parcial: "Recuperação parcial",
  ausencia_de_recuperacao: "Ausência de recuperação",
  resultado_inconclusivo: "Inconclusivo",
};
export const recoveryMeta: Record<RecoveryStatus, [Tone, Shape]> = {
  recuperacao_completa: ["ok", "dot"],
  recuperacao_parcial: ["info", "half"],
  ausencia_de_recuperacao: ["risk", "diamond"],
  resultado_inconclusivo: ["neutral", "dash"],
};
export const RecoveryBadge = ({ value }: { value: RecoveryStatus | null }) =>
  value === null ? <StatusLabel tone="neutral" shape="ring">Por avaliar</StatusLabel> : <StatusLabel tone={recoveryMeta[value][0]} shape={recoveryMeta[value][1]}>{recoveryLabel[value]}</StatusLabel>;

export const stageLabel: Record<Stage, string> = { contract: "Contrato", detection: "Deteção", investigation: "Investigação", intervention: "Intervenção", recovery: "Recuperação" };

/** Value without an HTTP source in L01: always visibly marked. */
export function DemoOnly({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {children}
      <span title="Sem fonte HTTP atual — campo só de demonstração" className="rounded border border-demo-foreground/25 bg-demo px-1 font-mono text-[9px] leading-4 tracking-wide text-demo-foreground">DEMO</span>
    </span>
  );
}

export function DemoTag({ children = "Demonstração" }: { children?: ReactNode }) {
  return <span className="inline-flex h-5 items-center rounded border border-demo-foreground/25 bg-demo px-1.5 font-mono text-[10px] tracking-wide text-demo-foreground">{children}</span>;
}

/** Thin page bar: breadcrumb, title, count and right-side actions. */
export function PageBar({ crumbs = [], title, count, actions }: { crumbs?: { label: string; to: string }[]; title: string; count?: number; actions?: ReactNode }) {
  return (
    <div className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border-subtle px-4 py-2 sm:px-6">
      <nav aria-label="Trilho" className="flex min-w-0 items-center gap-1.5 text-[13px]">
        {crumbs.map((c) => (
          <span key={c.to} className="flex items-center gap-1.5">
            <Link to={c.to} className="text-muted-foreground hover:text-foreground">{c.label}</Link>
            <ChevronRight className="size-3.5 text-subtle-foreground" />
          </span>
        ))}
        <h1 className="truncate font-medium">{title}</h1>
        {count !== undefined && <span className="font-mono text-xs text-subtle-foreground">{count}</span>}
      </nav>
      <DemoTag />
      {actions && <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Intro line below the page bar. */
export function PageIntro({ title, description }: { title: string; description?: string }) {
  return (
    <div className="px-4 pt-6 pb-4 sm:px-6">
      <h2 className="page-title">{title}</h2>
      {description && <p className="mt-1 max-w-2xl text-muted-foreground">{description}</p>}
    </div>
  );
}

export function Section({ title, aside, children, className, flush }: { title: string; aside?: ReactNode; children: ReactNode; className?: string; flush?: boolean }) {
  return (
    <section className={className}>
      <header className="flex h-9 items-center justify-between gap-3 border-b border-border-subtle">
        <h3 className="text-[13px] font-medium">{title}</h3>
        {aside}
      </header>
      <div className={flush ? "" : "py-3"}>{children}</div>
    </section>
  );
}

const noticeTone: Record<Tone, string> = { ok: "border-l-ok", warn: "border-l-warn", risk: "border-l-risk", info: "border-l-info", neutral: "border-l-neutral" };
export function Notice({ children, tone = "warn" }: { children: ReactNode; tone?: Tone }) {
  return <div role="note" className={cn("rounded-md border border-l-2 border-border-subtle bg-surface px-3 py-2 text-[13px] text-muted-foreground", noticeTone[tone])}>{children}</div>;
}

/** Write actions are disabled in L02. */
export function LockedAction({ children }: { children: ReactNode }) {
  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span tabIndex={0} className="inline-flex rounded-md">
            <button type="button" disabled aria-disabled className="inline-flex h-8 cursor-not-allowed items-center gap-1.5 rounded-md border px-2.5 text-[13px] text-subtle-foreground max-sm:h-11">
              <Lock className="size-3" />
              {children}
            </button>
          </span>
        </TooltipTrigger>
        <TooltipContent>Disponível após integração segura</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="eyebrow mb-0.5">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** Right-hand property list (label / value pairs, no frame). */
export function PropertyPanel({ groups }: { groups: { title: string; items: { label: string; value: ReactNode }[] }[] }) {
  return (
    <aside className="flex flex-col gap-6">
      {groups.map((g) => (
        <div key={g.title}>
          <div className="eyebrow mb-2">{g.title}</div>
          <dl className="flex flex-col gap-2">
            {g.items.map((i) => (
              <div key={i.label} className="grid grid-cols-[7rem_1fr] items-baseline gap-2">
                <dt className="text-subtle-foreground">{i.label}</dt>
                <dd className="min-w-0">{i.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </aside>
  );
}

export function MetricStrip({ items }: { items: { label: string; value: ReactNode; glyph?: ReactNode }[] }) {
  return (
    <div className="grid grid-cols-2 border-y border-border-subtle sm:flex sm:divide-x sm:divide-border-subtle">
      {items.map((m) => (
        <div key={m.label} className="flex-1 px-4 py-3 sm:px-6 max-sm:border-b max-sm:border-border-subtle max-sm:odd:border-r">
          <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">{m.glyph}{m.label}</div>
          <div className="mt-0.5 text-[22px] font-semibold tracking-tight tabular-nums">{m.value}</div>
        </div>
      ))}
    </div>
  );
}

export function ListGroupHeader({ children, count }: { children: ReactNode; count?: number }) {
  return (
    <div className="flex h-8 items-center gap-2 border-b border-border-subtle bg-surface px-4 text-[12px] font-medium sm:px-6">
      {children}
      {count !== undefined && <span className="font-mono text-subtle-foreground">{count}</span>}
    </div>
  );
}

export function ActivityFeed({ items }: { items: { id: string; when: string; who: ReactNode; text: ReactNode }[] }) {
  return (
    <ol className="relative flex flex-col gap-3 border-l border-border-subtle pl-4">
      {items.map((a) => (
        <li key={a.id} className="relative">
          <span className="absolute top-[7px] -left-[19.5px] size-[7px] rounded-full border border-border bg-background" />
          <div className="text-muted-foreground">
            <span className="font-medium text-foreground">{a.who}</span> · {a.text}
          </div>
          <div className="font-mono text-[11px] text-subtle-foreground">{a.when}</div>
        </li>
      ))}
    </ol>
  );
}

const evidenceKinds = {
  facts: { label: "Factos", tone: "ok", shape: "dot" },
  hypotheses: { label: "Hipóteses", tone: "info", shape: "ring" },
  contradictions: { label: "Contradições", tone: "risk", shape: "diamond" },
  missing: { label: "Informação em falta", tone: "warn", shape: "dash" },
} as const;
export function EvidenceBlock({ kind, items }: { kind: keyof typeof evidenceKinds; items: string[] }) {
  const k = evidenceKinds[kind];
  return (
    <div className="border-b border-border-subtle py-3 last:border-0">
      <div className="mb-1.5 flex items-center gap-2 text-[12px] font-medium uppercase tracking-wide">
        <StatusDot tone={k.tone} shape={k.shape} />
        {k.label}
        <span className="font-mono text-subtle-foreground">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="pl-[18px] text-subtle-foreground">Nenhum registo.</p>
      ) : (
        <ul className="flex flex-col gap-1 pl-[18px]">{items.map((x) => <li key={x}>{x}</li>)}</ul>
      )}
    </div>
  );
}

export function FilterChips<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: { value: T; label: string; count?: number }[] }) {
  return (
    <div role="radiogroup" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn("inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-[12px] max-sm:h-10", value === o.value ? "border-border bg-surface-raised text-foreground" : "border-transparent text-muted-foreground hover:bg-surface-hover hover:text-foreground")}
        >
          {o.label}
          {o.count !== undefined && <span className="font-mono text-subtle-foreground">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="py-10 text-center text-muted-foreground">{children}</p>;
}

export function KbdHint({ children }: { children: ReactNode }) {
  return <kbd className="rounded border px-1 font-mono text-[10px] text-subtle-foreground">{children}</kbd>;
}

