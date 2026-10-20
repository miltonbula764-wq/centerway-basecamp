import { createFileRoute, Link, Outlet, useNavigate, useRouteContext } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronsUpDown,
  Database,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Menu,
  Plus,
  Settings,
  Target,
  Users,
} from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { membershipsQuery } from "@/lib/memberships";
import {
  pickTenant,
  readPreferredTenant,
  roleLabel,
  setActiveTenantId,
  TenantContext,
  useTenant,
  writePreferredTenant,
  type TenantCtx,
  type TenantInfo,
} from "@/lib/tenant";
import { NotificationBadge } from "@/components/app/operational-inbox";
import { ErrorState, Loading } from "@/components/app/ui-bits";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

export const Route = createFileRoute("/_authenticated/app")({
  head: () => ({
    meta: [
      { title: "CENTERWAY" },
      { name: "description", content: "Área de trabalho CENTERWAY." },
      { property: "og:title", content: "CENTERWAY" },
      { property: "og:description", content: "Área de trabalho CENTERWAY." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AppLayout,
});

const nav = [
  { to: "/app", label: "Visão geral", icon: LayoutDashboard, exact: true },
  { to: "/app/clientes", label: "Clientes", icon: Users },
  { to: "/app/perfil", label: "Perfil de valor", icon: Target },
  { to: "/app/dados", label: "Dados", icon: Database },
  { to: "/app/acompanhamento", label: "Acompanhamento", icon: LayoutDashboard },
  { to: "/app/casos", label: "Casos", icon: FolderKanban },
  { to: "/app/configuracoes", label: "Configurações", icon: Settings },
] as const;

function AppLayout() {
  const { user } = useRouteContext({ from: "/_authenticated" });
  const qc = useQueryClient();
  const navigate = useNavigate();
  const memberships = useQuery(membershipsQuery(user.id));
  const [selected, setSelected] = useState<string | null>(null);

  // Revalidate the stored preference against real memberships on every (re)load.
  useEffect(() => {
    if (!memberships.data) return;
    if (memberships.data.length === 0) {
      navigate({ to: "/onboarding", replace: true });
      return;
    }
    const next = pickTenant(memberships.data, selected ?? readPreferredTenant());
    if (next !== selected) {
      if (selected) qc.removeQueries({ queryKey: ["t"] });
      setSelected(next);
      writePreferredTenant(next);
    }
  }, [memberships.data, selected, navigate, qc]);

  const tenant: TenantInfo | undefined = memberships.data?.find((t) => t.id === selected);
  setActiveTenantId(tenant?.id ?? null);
  const previousAccess = useRef<string | null>(null);
  const access = tenant ? `${tenant.id}:${tenant.role}` : null;
  useEffect(() => {
    if (previousAccess.current !== null && previousAccess.current !== access) {
      const [oldTenant, oldRole] = previousAccess.current.split(":");
      const key = tenant?.id === oldTenant ? ["t", oldTenant, "team", oldRole] : ["t", oldTenant];
      void qc.cancelQueries({ queryKey: key });
      qc.removeQueries({ queryKey: key });
    }
    previousAccess.current = access;
  }, [access, qc, tenant?.id]);


  const switchTenant = useCallback(
    (id: string) => {
      if (id === selected) return;
      setActiveTenantId(null);
      qc.removeQueries({ queryKey: ["t"] });
      writePreferredTenant(id);
      setSelected(id);
      qc.invalidateQueries({ queryKey: ["memberships"] });
      navigate({ to: "/app" });
    },
    [qc, selected, navigate],
  );

  const signOut = useCallback(async () => {
    setActiveTenantId(null);
    await qc.cancelQueries();
    qc.clear();
    writePreferredTenant(null);
    await supabase.auth.signOut();
    navigate({ to: "/auth", search: { redirect: undefined }, replace: true });
  }, [qc, navigate]);

  const ctx = useMemo<TenantCtx | null>(
    () =>
      tenant
        ? {
            tenant,
            tenants: memberships.data ?? [],
            user,
            switchTenant,
            signOut,
            canWrite: tenant.role === "admin" || tenant.role === "operator",
            isAdmin: tenant.role === "admin",
          }
        : null,
    [tenant, memberships.data, user, switchTenant, signOut],
  );

  if (memberships.isError)
    return (
      <div className="p-8">
        <ErrorState message="Não foi possível carregar as suas empresas." onRetry={() => memberships.refetch()} />
      </div>
    );
  if (!ctx)
    return (
      <div className="p-8">
        <Loading />
      </div>
    );

  return (
    <TenantContext.Provider value={ctx}>
      <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
        <aside className="sticky top-0 hidden h-screen flex-col border-r border-sidebar-border bg-sidebar md:flex">
          <SidebarContent />
        </aside>
        <div className="min-w-0">
          <MobileBar />
          <main className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8 md:py-8">
            <div key={ctx.tenant.id}>
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </TenantContext.Provider>
  );
}

function MobileBar() {
  const [open, setOpen] = useState(false);
  return (
    <div className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-background/90 px-4 py-3 backdrop-blur md:hidden">
      <Brand />
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Abrir menu">
            <Menu className="h-5 w-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="flex w-72 flex-col border-sidebar-border bg-sidebar p-0">
          <SheetTitle className="sr-only">Menu</SheetTitle>
          <SidebarContent onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2">
      <div className="grid h-6 w-6 place-items-center rounded bg-primary font-mono text-[11px] font-bold text-primary-foreground">C</div>
      <span className="font-mono text-xs tracking-[0.2em]">CENTERWAY</span>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { tenant, tenants, user, switchTenant, signOut } = useTenant();
  return (
    <>
      <div className="hidden px-4 pb-2 pt-5 md:block">
        <Brand />
      </div>
      <div className="px-3 pt-4 md:pt-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex w-full items-center justify-between gap-2 rounded-md border border-sidebar-border bg-sidebar-accent/50 px-3 py-2 text-left hover:bg-sidebar-accent">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{tenant.name}</span>
                <span className="block text-xs text-muted-foreground">{roleLabel[tenant.role]}</span>
              </span>
              <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-60">
            <DropdownMenuLabel className="text-xs text-muted-foreground">Empresas</DropdownMenuLabel>
            {tenants.map((t) => (
              <DropdownMenuItem key={t.id} onSelect={() => { switchTenant(t.id); onNavigate?.(); }}>
                <span className="flex-1 truncate">{t.name}</span>
                {t.id === tenant.id && <Check className="h-4 w-4" />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link to="/onboarding">
                <Plus className="h-4 w-4" /> Nova empresa
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <NotificationBadge onNavigate={onNavigate} />
      <nav className="mt-4 flex-1 space-y-0.5 px-3" aria-label="Principal">
        {nav.map((item) => (
          <Link
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            activeOptions={{ exact: "exact" in item ? item.exact : false }}
            className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            activeProps={{ className: "bg-sidebar-accent !text-sidebar-accent-foreground font-medium" }}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="border-t border-sidebar-border p-3">
        <p className="truncate px-2.5 pb-2 text-xs text-muted-foreground" title={user.email}>
          {user.email}
        </p>
        <button
          onClick={() => signOut()}
          className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent"
        >
          <LogOut className="h-4 w-4" /> Terminar sessão
        </button>
      </div>
    </>
  );
}

