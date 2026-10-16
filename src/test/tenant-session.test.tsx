import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { SubjectDialog } from "@/components/app/subject-dialog";
import { assertActiveTenant, setActiveTenantId, TENANT_CHANGED, tk, useTenant } from "@/lib/tenant";

const mocks = vi.hoisted(() => ({ navigate: vi.fn(), signOut: vi.fn(), insert: vi.fn() }));
const tenants = [
  { id: "fixture-A", name: "Empresa A", role: "admin", subject_unit_type: "organization" },
  { id: "fixture-B", name: "Empresa B", role: "viewer", subject_unit_type: "organization" },
];

vi.mock("@/integrations/supabase/client", () => ({
  supabase: { auth: { signOut: mocks.signOut }, from: () => ({ insert: mocks.insert }) },
}));
vi.mock("@/lib/memberships", () => ({
  membershipsQuery: () => ({ queryKey: ["memberships", "fixture-user"], queryFn: async () => tenants }),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  useRouteContext: () => ({ user: { id: "fixture-user", email: "fixture@example.invalid" } }),
  useNavigate: () => mocks.navigate,
  Link: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  Outlet: () => <TestSurface />,
}));
// Keep real layout/context/query/mutation behavior; replace only menu presentation.
vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => null,
  DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => <button onClick={onSelect}>{children}</button>,
}));

import { Route } from "@/routes/_authenticated/app";

let resolveA: (value: string) => void;
let pendingA: Promise<string>;
function TestSurface() {
  const { tenant, canWrite } = useTenant();
  const [open, setOpen] = useState(false);
  const result = useQuery({ queryKey: tk(tenant.id, "controlled-read"), queryFn: () => tenant.id === "fixture-A" ? pendingA : Promise.resolve("Dados B") });
  return <>
    <div data-testid="active-tenant">{tenant.id}</div>
    <div>{result.data}</div>
    {canWrite && <button onClick={() => setOpen(true)}>Abrir formulário</button>}
    {canWrite && <SubjectDialog open={open} onOpenChange={setOpen} />}
  </>;
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const Layout = Route.options.component;
  if (!Layout) throw new Error("Missing app layout");
  render(<QueryClientProvider client={qc}><Layout /></QueryClientProvider>);
  return qc;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setActiveTenantId(null);
  pendingA = new Promise<string>((resolve) => { resolveA = resolve; });
  mocks.signOut.mockResolvedValue({ error: null });
  mocks.insert.mockResolvedValue({ error: null });
});
afterEach(() => { cleanup(); setActiveTenantId(null); });

describe("Existing tenant/session UI with controlled requests (not real login)", () => {
  it("drops A cache and its open form; a late A read cannot appear in B", async () => {
    const qc = mount();
    await waitFor(() => expect(screen.getByTestId("active-tenant")).toHaveTextContent("fixture-A"));
    qc.setQueryData(tk("fixture-A", "cached-secret"), "Segredo A");
    fireEvent.click(screen.getByRole("button", { name: "Abrir formulário" }));
    fireEvent.change(await screen.findByLabelText("Referência externa"), { target: { value: "cliente-A" } });
    fireEvent.click(screen.getByRole("button", { name: "Empresa B" }));
    await screen.findByText("Dados B");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abrir formulário" })).not.toBeInTheDocument();
    await act(async () => resolveA("Dados privados A"));
    expect(screen.queryByText("Dados privados A")).not.toBeInTheDocument();
    expect(qc.getQueryCache().findAll({ queryKey: ["t", "fixture-A"] })).toHaveLength(0);
    expect(localStorage.getItem("centerway.selectedTenant")).toBe("fixture-B");
    expect(mocks.insert).not.toHaveBeenCalled();
  });

  it("rejects an A preview submitted after switching to B before any request", async () => {
    mount();
    await waitFor(() => expect(screen.getByTestId("active-tenant")).toHaveTextContent("fixture-A"));
    const preview = { tenantId: "fixture-A" };
    const submitCapturedPreview = () => { assertActiveTenant(preview.tenantId); mocks.insert(preview); };
    fireEvent.click(screen.getByRole("button", { name: "Empresa B" }));
    await screen.findByText("Dados B");
    expect(submitCapturedPreview).toThrow(TENANT_CHANGED);
    expect(mocks.insert).not.toHaveBeenCalled();
  });

  it("cancels pending queries and clears cache/preference before sign-out and replacement navigation", async () => {
    const qc = mount();
    await waitFor(() => expect(screen.getByTestId("active-tenant")).toHaveTextContent("fixture-A"));
    const cancel = vi.spyOn(qc, "cancelQueries");
    mocks.signOut.mockImplementation(async () => {
      expect(cancel).toHaveBeenCalled();
      expect(qc.getQueryCache().getAll()).toHaveLength(0);
      expect(localStorage.getItem("centerway.selectedTenant")).toBeNull();
      expect(() => assertActiveTenant("fixture-A")).toThrow(TENANT_CHANGED);
      return { error: null };
    });
    fireEvent.click(screen.getByRole("button", { name: "Terminar sessão" }));
    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith({ to: "/auth", search: { redirect: undefined }, replace: true }));
    expect(mocks.signOut).toHaveBeenCalledTimes(1);
    await act(async () => resolveA("Dados privados A"));
    expect(qc.getQueryCache().findAll({ queryKey: ["t"] })).toHaveLength(0);
  });
});