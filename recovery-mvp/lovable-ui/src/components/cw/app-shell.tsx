import { useState, type ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { LayoutGrid, Users, FileCheck2, SearchCheck, Workflow, LineChart, BookOpen, Menu, FlaskConical } from "lucide-react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const groups = [
  { label: "Operação", items: [
    { to: "/app", label: "Visão Geral", icon: LayoutGrid, exact: true },
    { to: "/app/clientes", label: "Clientes", icon: Users },
  ] },
  { label: "Valor", items: [
    { to: "/app/contratos", label: "Contratos de Valor", icon: FileCheck2 },
    { to: "/app/recuperacao", label: "Recuperação", icon: LineChart },
  ] },
  { label: "Análise", items: [
    { to: "/app/investigacoes", label: "Investigações", icon: SearchCheck },
    { to: "/app/intervencoes", label: "Intervenções", icon: Workflow },
  ] },
] as const;

/** Own mark: two converging strokes meeting at a centre point. */
function Mark() {
  return (
    <svg viewBox="0 0 16 16" className="size-4 text-primary" aria-hidden>
      <path d="M2 3 L8 9 L14 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="8" cy="13" r="1.6" fill="currentColor" />
    </svg>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-3 py-4">
      <Mark />
      <div>
        <div className="font-mono text-[12px] font-semibold tracking-[0.24em]">CENTERWAY</div>
        <div className="text-[11px] text-subtle-foreground">Inteligência de valor do cliente</div>
      </div>
    </div>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const isOn = (to: string, exact?: boolean) => (exact ? path === to || path === to + "/" : path.startsWith(to));
  const item = (to: string, label: string, Icon: typeof LayoutGrid, exact?: boolean) => {
    const on = isOn(to, exact);
    return (
      <Link
        key={to}
        to={to}
        onClick={onNavigate}
        aria-current={on ? "page" : undefined}
        className={cn(
          "flex h-[30px] items-center gap-2.5 rounded-md px-2.5 text-[13px] max-lg:h-11",
          on ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground",
        )}
      >
        <Icon className={cn("size-[15px]", on ? "text-foreground" : "text-subtle-foreground")} />
        {label}
      </Link>
    );
  };
  return (
    <nav className="flex flex-1 flex-col px-2">
      {groups.map((g) => (
        <div key={g.label} className="mb-4">
          <div className="mb-1 px-2.5 text-[11px] font-medium text-subtle-foreground">{g.label}</div>
          <div className="flex flex-col gap-px">{g.items.map((i) => item(i.to, i.label, i.icon, "exact" in i ? i.exact : false))}</div>
        </div>
      ))}
      <div className="mt-auto border-t border-sidebar-border py-2">{item("/app/sobre", "Sobre esta demonstração", BookOpen)}</div>
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-sidebar">
      <div className="sticky top-0 z-40 flex h-7 items-center justify-center gap-2 border-b border-demo-foreground/15 bg-demo px-4 text-[11px] text-demo-foreground">
        <FlaskConical className="size-3" />
        <span className="font-medium">Ambiente de demonstração</span>
        <span className="hidden opacity-75 sm:inline">· API pública, dados exclusivamente sintéticos</span>
      </div>

      <aside className="fixed top-7 bottom-0 left-0 z-30 hidden w-[232px] flex-col bg-sidebar lg:flex">
        <Brand />
        <NavList />
      </aside>

      <header className="sticky top-7 z-30 flex h-14 items-center justify-between border-b border-border-subtle bg-sidebar px-3 lg:hidden">
        <Brand />
        <button aria-label="Abrir navegação" onClick={() => setOpen(true)} className="flex size-11 items-center justify-center rounded-md hover:bg-surface-hover">
          <Menu className="size-5" />
        </button>
      </header>
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="flex w-72 flex-col border-sidebar-border bg-sidebar p-0">
          <SheetTitle className="sr-only">Navegação</SheetTitle>
          <Brand />
          <NavList onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>

      <main className="lg:py-2 lg:pr-2 lg:pl-[232px]">
        <div className="min-h-[calc(100vh-1.75rem-1rem)] bg-background lg:rounded-[10px] lg:border lg:border-border-subtle">{children}</div>
      </main>
    </div>
  );
}

