// Controlled request races only. Real JWT/RLS and persistence are tested in PostgreSQL/browser suites.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { FollowupQueue } from "@/components/app/followup-queue";
import { setActiveTenantId } from "@/lib/tenant";
const mocks = vi.hoisted(() => ({ rpc: vi.fn(), navigate: vi.fn() }));
const tenants = [
  { id: "A", name: "Empresa A", role: "admin", subject_unit_type: "organization" },
  { id: "B", name: "Empresa B", role: "viewer", subject_unit_type: "organization" },
];
vi.mock("@/integrations/supabase/client", () => ({ supabase: { rpc: mocks.rpc } }));
vi.mock("@/lib/memberships", () => ({
  membershipsQuery: () => ({ queryKey: ["memberships", "user"], queryFn: async () => tenants }),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  useRouteContext: () => ({ user: { id: "user", email: "test@example.invalid" } }),
  useNavigate: () => mocks.navigate,
  Link: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Outlet: () => <FollowupQueue />,
}));
vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => null,
  DropdownMenuItem: ({ children, onSelect }: { children: ReactNode; onSelect?: () => void }) => (
    <button onClick={onSelect}>{children}</button>
  ),
}));
import { Route } from "@/routes/_authenticated/app";
const page = (tenant: string) => ({
  tenant_id: tenant,
  server_now: "2026-01-01T00:00:00Z",
  items: [],
  has_more: false,
  next_cursor: null,
});
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  setActiveTenantId(null);
});
afterEach(() => {
  cleanup();
  setActiveTenantId(null);
});
function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Layout = Route.options.component!;
  render(
    <QueryClientProvider client={client}>
      <Layout />
    </QueryClientProvider>,
  );
  return client;
}
it("cancels an A queue request, drops its cache and rejects its late response after actual layout switches to B", async () => {
  let finish: (value: unknown) => void = () => {};
  let signalA: AbortSignal | undefined;
  mocks.rpc.mockImplementation((_name, args) => ({
    abortSignal: (signal: AbortSignal) =>
      args._tenant_id === "A"
        ? ((signalA = signal),
          new Promise((resolve) => {
            finish = resolve;
          }))
        : Promise.resolve({ data: page("B"), error: null }),
  }));
  const client = mount();
  await waitFor(() => expect(mocks.rpc).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "Empresa B" }));
  await screen.findByText(/Empresa B · Estados persistidos/);
  await act(async () =>
    finish({
      data: {
        ...page("A"),
        items: [{ tenant_id: "A", entry_key: "private-A", display_name: "Segredo A" }],
      },
      error: null,
    }),
  );
  expect(signalA?.aborted).toBe(true);
  expect(screen.queryByText("Segredo A")).not.toBeInTheDocument();
  expect(client.getQueryCache().findAll({ queryKey: ["t", "A"] })).toHaveLength(0);
  expect(localStorage.getItem("centerway.selectedTenant")).toBe("B");
});
it("refresh preserves active tenant and filters; mismatched response identities are rejected", async () => {
  mocks.rpc.mockImplementation((_name, args) => ({
    abortSignal: () => Promise.resolve({ data: page(args._tenant_id), error: null }),
  }));
  mount();
  await screen.findByText("Sem entradas para estes filtros");
  fireEvent.change(screen.getByLabelText("Cliente"), { target: { value: "client-42" } });
  fireEvent.change(screen.getByLabelText("Indicador"), { target: { value: "minutes" } });
  fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "result_open" } });
  fireEvent.click(screen.getByRole("button", { name: "Filtrar fila" }));
  await waitFor(() =>
    expect(mocks.rpc).toHaveBeenLastCalledWith(
      "core_followup_queue",
      expect.objectContaining({
        _tenant_id: "A",
        _client: "client-42",
        _indicator: "minutes",
        _category: "result_open",
      }),
    ),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Atualizar fila" })).not.toBeDisabled(),
  );
  mocks.rpc.mockImplementation(() => ({
    abortSignal: () => Promise.resolve({ data: page("B"), error: null }),
  }));
  fireEvent.click(screen.getByRole("button", { name: "Atualizar fila" }));
  await screen.findByText(/Identidade da empresa não corresponde/);
  expect(mocks.rpc).toHaveBeenLastCalledWith(
    "core_followup_queue",
    expect.objectContaining({ _tenant_id: "A", _client: "client-42", _indicator: "minutes" }),
  );
});
it("monitoring filters and refresh use tenant keys; read queries never invoke preparation", async () => {
  mocks.rpc.mockImplementation((name, args) => ({
    abortSignal: () =>
      Promise.resolve({
        data:
          name === "scheduled_reviews"
            ? { ...page(args._tenant_id), scan: null, attempts: [] }
            : page(args._tenant_id),
        error: null,
      }),
  }));
  mount();
  await screen.findByText("Sem revisões preparadas para estes filtros.");
  fireEvent.change(screen.getByLabelText("Estado da revisão"), { target: { value: "waiting" } });
  fireEvent.change(screen.getByLabelText("Indicador da revisão"), { target: { value: "cycle" } });
  fireEvent.click(screen.getByRole("button", { name: "Filtrar revisões" }));
  await waitFor(() =>
    expect(mocks.rpc).toHaveBeenCalledWith(
      "scheduled_reviews",
      expect.objectContaining({ _tenant_id: "A", _status: "waiting", _indicator: "cycle" }),
    ),
  );
  expect(mocks.rpc.mock.calls.every(([name]) => name !== "prepare_scheduled_reviews")).toBe(true);
});
it("late monitoring preparation after tenant switch cannot publish a success or repopulate old tenant cache", async () => {
  let finish: (value: unknown) => void = () => {};
  mocks.rpc.mockImplementation((name, args) =>
    name === "prepare_scheduled_reviews"
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : {
          abortSignal: () =>
            Promise.resolve({
              data:
                name === "scheduled_reviews"
                  ? { ...page(args._tenant_id), scan: null, attempts: [] }
                  : page(args._tenant_id),
              error: null,
            }),
        },
  );
  const client = mount();
  await screen.findByText("Sem revisões preparadas para estes filtros.");
  fireEvent.click(screen.getByRole("button", { name: "Preparar próximo lote de revisões" }));
  await waitFor(() =>
    expect(mocks.rpc).toHaveBeenCalledWith(
      "prepare_scheduled_reviews",
      expect.objectContaining({ _tenant_id: "A" }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Empresa B" }));
  await screen.findByText(/Empresa B · Estados persistidos/);
  await act(async () =>
    finish({ data: { tenant_id: "A", status: "completed", processed: 50 }, error: null }),
  );
  expect(screen.queryByText(/Lote preparado:/)).not.toBeInTheDocument();
  expect(client.getQueryCache().findAll({ queryKey: ["t", "A"] })).toHaveLength(0);
  expect(
    screen.queryByRole("button", { name: "Preparar próximo lote de revisões" }),
  ).not.toBeInTheDocument();
});
