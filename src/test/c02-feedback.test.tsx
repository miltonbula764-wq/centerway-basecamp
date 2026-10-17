import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { DeteriorationPanel } from "@/components/app/deterioration-panel";
import { setActiveTenantId, TenantContext, type TenantCtx } from "@/lib/tenant";

const mocks = vi.hoisted(() => ({
  from: vi.fn(), rpc: vi.fn(), success: vi.fn(), subject: "subject-a",
  queries: [] as { table: string; filters: Record<string, unknown> }[],
}));
vi.mock("@/integrations/supabase/client", () => ({ supabase: { from: mocks.from, rpc: mocks.rpc } }));
vi.mock("sonner", () => ({ toast: { success: mocks.success, info: vi.fn() } }));
// The actual customer route, C02, C03 and query hooks render; only router inputs are controlled.
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: unknown) => ({ options, useParams: () => ({ subjectId: mocks.subject }) }),
  Link: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}));
import { Route } from "@/routes/_authenticated/app.clientes.$subjectId";

const A = "tenant-a";
const B = "tenant-b";
const SUBJECT = "subject-a";
const OTHER_SUBJECT = "subject-b";
const PROFILE = "profile-approved";
const iso = "2026-10-01T00:00:00Z";

function ctx(tenantId = A, role: "admin" | "operator" | "viewer" = "operator"): TenantCtx {
  return {
    tenant: { id: tenantId, name: tenantId, subject_unit_type: "organization", role },
    tenants: [], user: { id: "synthetic", email: "fixture@example.invalid" },
    switchTenant: () => {}, signOut: async () => {},
    canWrite: role !== "viewer", isAdmin: role === "admin",
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}
function runRow(id: string) {
  return { id, profile_version: 1, algorithm_version: "c02-v2", as_of: iso, data_cutoff: iso,
    observation_count: 3, revision_of: null, summary: { outcome_candidates: 0, usage_candidates: 0, insufficient: 0 }, created_at: iso };
}
function queries() {
  mocks.from.mockImplementation((table: string) => {
    const filters: Record<string, unknown> = {};
    const c: Record<string, unknown> = {};
    c["select"] = () => c;
    c["eq"] = (key: string, value: unknown) => { filters[key] = value; return c; };
    for (const method of ["order", "limit", "maybeSingle"]) c[method] = () => c;
    c["then"] = (resolve: (v: unknown) => unknown, reject: (e: unknown) => unknown) => {
      mocks.queries.push({ table, filters });
      let data: unknown = [];
      if (table === "subjects") data = { id: filters["id"], external_ref: filters["id"], display_name: null, created_at: iso, updated_at: iso };
      if (table === "tenant_value_profiles") data = [{ id: PROFILE, status: "approved", version: 1, promise: "Synthetic promise" }];
      if (table === "c02_runs") data = [runRow(`${filters["subject_id"]}-run-1`), runRow(`${filters["subject_id"]}-run-2`)];
      if (table === "c03_bundles") data = [{
        id: `bundle-${filters["run_id"]}`, run_id: filters["run_id"], algorithm_version: "c03-v1", c02_algorithm_version: "c02-v2",
        c02_input_hash: "a".repeat(64), data_cutoff: iso, content_hash: "b".repeat(64), revision_of: null,
        summary: { complete: 0, insufficient: 0, context_facts: 0, stored_refs: 0 }, created_at: iso,
      }];
      return Promise.resolve({ data, error: null }).then(resolve, reject);
    };
    return c;
  });
}
function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}
function mount(role: "admin" | "operator" | "viewer" = "operator") {
  const qc = client();
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  const tree = (tenantId: string, subjectId: string) => (
    <QueryClientProvider client={qc}>
      <TenantContext.Provider value={ctx(tenantId, role)}>
        <DeteriorationPanel subjectId={subjectId} profileId={PROFILE} />
      </TenantContext.Provider>
    </QueryClientProvider>
  );
  const view = render(tree(A, SUBJECT));
  return { qc, invalidate, unmount: view.unmount, rerender: (tenant: string, subject: string) => view.rerender(tree(tenant, subject)) };
}

beforeEach(() => {
  vi.clearAllMocks(); mocks.queries.length = 0; mocks.subject = SUBJECT;
  setActiveTenantId(A); queries();
});
afterEach(() => { cleanup(); setActiveTenantId(null); });

const contexts = ["tenant", "subject", "unmount", "A-B-A"] as const;
for (const outcome of ["success", "error"] as const) {
  describe(`C02 late ${outcome} (controlled RPC, not a backend permission test)`, () => {
    it.each(contexts)("ignores stale feedback after %s", async (change) => {
      const rpc = deferred<unknown>();
      mocks.rpc.mockReturnValue(rpc.promise);
      const m = mount();
      fireEvent.click(await screen.findByRole("button", { name: /Analisar agora/ }));
      // Positive request sentinel BEFORE changing any identity.
      await waitFor(() => expect(mocks.rpc).toHaveBeenCalledTimes(1));
      expect(mocks.rpc).toHaveBeenCalledWith("run_deterioration_analysis", {
        _tenant_id: A, _subject_id: SUBJECT, _expected_profile_id: PROFILE,
      });
      if (change === "tenant" || change === "A-B-A") {
        setActiveTenantId(B); m.rerender(B, SUBJECT);
      }
      if (change === "subject") m.rerender(A, OTHER_SUBJECT);
      if (change === "unmount") m.unmount();
      if (change === "A-B-A") { setActiveTenantId(A); m.rerender(A, SUBJECT); }
      await act(async () => {
        rpc.resolve(outcome === "success"
          ? { data: { run_id: "late-run-from-A", reused: false }, error: null }
          : { data: null, error: { message: "network down", code: "08006" } });
        await rpc.promise;
      });
      // Mutation success/error is dispatched AFTER its callbacks finish, even after unmount.
      await waitFor(() => expect(m.qc.getMutationCache().getAll()[0]?.state.status).toBe(outcome));
      expect(mocks.success).not.toHaveBeenCalled();
      expect(screen.queryByText("Sem ligação ao servidor. Tente novamente.")).not.toBeInTheDocument();
      expect(mocks.rpc).toHaveBeenCalledTimes(1); // never retarget an already-sent request
      if (outcome === "success") {
        expect(m.invalidate).toHaveBeenCalledWith({ queryKey: ["t", A, "c02_runs"] });
        expect(m.invalidate.mock.calls.some(([arg]) => arg?.queryKey?.[1] === B)).toBe(false);
      }
    });
  });
}

it.each(["admin", "operator"] as const)("preserves current-context success for %s", async (role) => {
  mocks.rpc.mockResolvedValue({ data: { run_id: `${SUBJECT}-run-2`, reused: true }, error: null });
  mount(role);
  await screen.findByRole("combobox", { name: "Análise" });
  fireEvent.click(screen.getByRole("button", { name: /Analisar agora/ }));
  await waitFor(() => expect(mocks.success).toHaveBeenCalledWith("Sem dados novos: foi reutilizada a análise existente."));
  expect(screen.getByRole("combobox", { name: "Análise" })).toHaveValue(`${SUBJECT}-run-2`);
});
it("preserves current-context errors", async () => {
  mocks.rpc.mockResolvedValue({ data: null, error: { message: "network down", code: "08006" } });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: /Analisar agora/ }));
  await screen.findByText("Sem ligação ao servidor. Tente novamente.");
});
it("viewer has no analyze action", async () => {
  mount("viewer");
  await screen.findByRole("combobox", { name: "Análise" });
  expect(screen.queryByRole("button", { name: /Analisar agora/ })).not.toBeInTheDocument();
  expect(mocks.rpc).not.toHaveBeenCalled();
});

it("customer detail keeps C03 on the selected C02 run of the CURRENT customer", async () => {
  const qc = client();
  const Detail = Route.options.component;
  if (!Detail) throw new Error("Customer detail component missing");
  const tree = () => <QueryClientProvider client={qc}><TenantContext.Provider value={ctx()}><Detail /></TenantContext.Provider></QueryClientProvider>;
  const view = render(tree());
  await screen.findByText(`bundle-${SUBJECT}-run-1`);
  fireEvent.change(screen.getByRole("combobox", { name: "Análise" }), { target: { value: `${SUBJECT}-run-2` } });
  await screen.findByText(`bundle-${SUBJECT}-run-2`);
  mocks.subject = OTHER_SUBJECT;
  view.rerender(tree());
  await screen.findByText(`bundle-${OTHER_SUBJECT}-run-1`);
  expect(screen.queryByText(`bundle-${SUBJECT}-run-2`)).not.toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Análise" })).toHaveValue(`${OTHER_SUBJECT}-run-1`);
  const bundleRequests = mocks.queries.filter((q) => q.table === "c03_bundles");
  expect(bundleRequests.map((q) => q.filters)).toEqual([
    { tenant_id: A, subject_id: SUBJECT, run_id: `${SUBJECT}-run-1` },
    { tenant_id: A, subject_id: SUBJECT, run_id: `${SUBJECT}-run-2` },
    { tenant_id: A, subject_id: OTHER_SUBJECT, run_id: `${OTHER_SUBJECT}-run-1` },
  ]);
  expect(mocks.rpc).not.toHaveBeenCalled(); // Selecting history never builds or analyzes automatically.
});
