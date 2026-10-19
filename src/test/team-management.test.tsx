// Controlled UI races. These tests do not claim real authentication or SQL authorization.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { TeamManagement } from "@/components/app/team-management";
import { setActiveTenantId } from "@/lib/tenant";
const mocks = vi.hoisted(() => ({ rpc: vi.fn(), navigate: vi.fn(), role: "admin" }));
vi.mock("@/integrations/supabase/client", () => ({ supabase: { rpc: mocks.rpc } }));
vi.mock("@/lib/memberships", () => ({
  membershipsQuery: () => ({
    queryKey: ["memberships", "user"],
    queryFn: async () => [
      { id: "A", name: "Empresa A", role: mocks.role, subject_unit_type: "organization" },
      { id: "B", name: "Empresa B", role: "viewer", subject_unit_type: "organization" },
    ],
  }),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options }),
  useRouteContext: () => ({ user: { id: "user", email: "test@example.invalid" } }),
  useNavigate: () => mocks.navigate,
  Link: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Outlet: () => <TeamManagement />,
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
function member(t: string, email: string | null) {
  return {
    id: "member-" + t,
    tenant_id: t,
    user_id: "user",
    email,
    role: mocks.role,
    created_at: "2026-01-01T00:00:00Z",
  };
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.role = "admin";
  localStorage.clear();
  setActiveTenantId(null);
  mocks.rpc.mockImplementation((name, args) => ({
    abortSignal: () =>
      Promise.resolve({
        data:
          name === "list_team_members"
            ? [member(args._tenant_id, mocks.role === "admin" ? "private-A@example.invalid" : null)]
            : [],
        error: null,
      }),
  }));
});
afterEach(() => {
  cleanup();
  setActiveTenantId(null);
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Layout = Route.options.component!;
  render(
    <QueryClientProvider client={client}>
      <Layout />
    </QueryClientProvider>,
  );
  return client;
}
it("drops private admin team cache and controls immediately on a server role refresh", async () => {
  const client = mount();
  await screen.findByText("private-A@example.invalid · Você");
  expect(screen.getByRole("form", { name: "Convidar colaborador" })).toBeInTheDocument();
  mocks.role = "viewer";
  await act(async () => {
    await client.invalidateQueries({ queryKey: ["memberships"] });
  });
  await waitFor(() =>
    expect(screen.queryByRole("form", { name: "Convidar colaborador" })).not.toBeInTheDocument(),
  );
  expect(screen.queryByText("private-A@example.invalid · Você")).not.toBeInTheDocument();
  expect(client.getQueryCache().findAll({ queryKey: ["t", "A", "team", "admin"] })).toHaveLength(0);
  expect(mocks.rpc).not.toHaveBeenCalledWith("set_member_role", expect.anything());
});
it("ignores a dispatched A invitation result after tenant switch and keeps its write targeted at A", async () => {
  let finish: (v: unknown) => void = () => {};
  const pending = new Promise((resolve) => {
    finish = resolve;
  });
  const normal = mocks.rpc.getMockImplementation()!;
  mocks.rpc.mockImplementation((name, args) =>
    name === "create_tenant_invitation" ? pending : normal(name, args),
  );
  const client = mount();
  await screen.findByText("private-A@example.invalid · Você");
  fireEvent.change(screen.getByLabelText("Email autorizado"), {
    target: { value: "invitee@example.invalid" },
  });
  fireEvent.change(screen.getByLabelText("Válido até"), { target: { value: "2026-12-01T00:00" } });
  fireEvent.submit(screen.getByRole("form", { name: "Convidar colaborador" }));
  await waitFor(() =>
    expect(mocks.rpc).toHaveBeenCalledWith(
      "create_tenant_invitation",
      expect.objectContaining({ _tenant_id: "A" }),
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Empresa B" }));
  await act(async () =>
    finish({ data: { id: "invite-A", token: "a".repeat(64), status: "pending" }, error: null }),
  );
  expect(screen.queryByLabelText("Ligação de convite")).not.toBeInTheDocument();
  expect(screen.queryByText(/Convite criado/)).not.toBeInTheDocument();
  expect(client.getQueryCache().findAll({ queryKey: ["t", "A"] })).toHaveLength(0);
  expect(mocks.rpc).not.toHaveBeenCalledWith(
    "create_tenant_invitation",
    expect.objectContaining({ _tenant_id: "B" }),
  );
});
