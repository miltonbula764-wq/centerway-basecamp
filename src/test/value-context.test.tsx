import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ValueContext } from "@/components/app/value-context";
import { historicalValueContextQuery, type ValueContextBundle } from "@/lib/queries";

const mocks = vi.hoisted(() => ({ from: vi.fn(), calls: [] as { table: string; filters: Record<string, unknown> }[] }));
vi.mock("@/integrations/supabase/client", () => ({ supabase: { from: mocks.from } }));
const bundle: ValueContextBundle = {
  id: "bundle-a", run_id: "run-a", c02_input_hash: "hash-a", c02_algorithm_version: "c02-v2",
  data_cutoff: "2026-10-01T00:00:00Z",
};
const run = { id: "run-a", tenant_id: "tenant-a", subject_id: "subject-a", profile_id: "profile-v1", profile_version: 1,
  input_hash: "hash-a", algorithm_version: "c02-v2", data_cutoff: bundle.data_cutoff };
const profile = { id: "profile-v1", tenant_id: "tenant-a", version: 1, status: "superseded",
  approved_at: "2026-09-01T00:00:00Z", promise: "Promessa histórica", expected_outcome: "Resultado contratado" };

type Handler = (table: string, filters: Record<string, unknown>) => unknown;
function backend(handler: Handler = table => table === "c02_runs" ? [run] : [profile]) {
  mocks.from.mockImplementation((table: string) => {
    const filters: Record<string, unknown> = {};
    const chain = {
      select: () => chain,
      eq: (key: string, value: unknown) => { filters[key] = value; return chain; },
      limit: () => chain,
      then: (resolve: (v: unknown) => unknown, reject: (e: unknown) => unknown) => {
        mocks.calls.push({ table, filters });
        return Promise.resolve(handler(table, filters)).then(data => ({ data, error: null })).then(resolve, reject);
      },
    };
    return chain;
  });
}
function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (tenantId = "tenant-a", subjectId = "subject-a", b = bundle) => (
    <QueryClientProvider client={qc}><ValueContext tenantId={tenantId} subjectId={subjectId} bundle={b} /></QueryClientProvider>
  );
  const view = render(tree());
  return { qc, change: (tenant: string, subject: string, b = bundle) => view.rerender(tree(tenant, subject, b)), unmount: view.unmount };
}
beforeEach(() => { mocks.from.mockReset(); mocks.calls.length = 0; backend(); });
afterEach(cleanup);

describe("Core input: historical promise, never a value conclusion", () => {
  it("exposes repeatable linked provenance through the existing query layer, without writes", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const query = historicalValueContextQuery("tenant-a", "subject-a", bundle);
    const first = await qc.fetchQuery(query);
    const second = await qc.fetchQuery(query);
    expect(first).toEqual({ profile, run, bundle });
    expect(second).toEqual(first);
    expect(mocks.calls.every(c => ["c02_runs", "tenant_value_profiles"].includes(c.table))).toBe(true);
    qc.clear();
  });
  it("joins the exact superseded profile, preserving the promise and expected outcome", async () => {
    mount();
    await screen.findByText("Promessa histórica");
    expect(screen.getByText("Resultado contratado")).toBeInTheDocument();
    expect(screen.getByText("Perfil v1 · aprovado para esta análise")).toBeInTheDocument();
    expect(mocks.calls).toEqual([
      { table: "c02_runs", filters: { tenant_id: "tenant-a", subject_id: "subject-a", id: "run-a" } },
      { table: "tenant_value_profiles", filters: { tenant_id: "tenant-a", id: "profile-v1" } },
    ]);
    expect(screen.getByText(/Conclusão de valor não disponível/)).toBeInTheDocument();
  });
  it("shows an absent expected outcome as missing, never zero or a default promise", async () => {
    backend(table => table === "c02_runs" ? [run] : [{ ...profile, expected_outcome: null }]);
    mount(); await screen.findByText("Não registado neste perfil.");
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
  it.each(["c02_runs", "tenant_value_profiles"])("does not infer value when %s is unavailable", async missing => {
    backend(table => table === missing ? [] : table === "c02_runs" ? [run] : [profile]);
    mount(); await screen.findByText(/Contexto histórico indisponível/);
    expect(screen.queryByText("Promessa histórica")).not.toBeInTheDocument();
  });
  it.each([
    { tenant_id: "tenant-b" }, { subject_id: "subject-b" }, { id: "run-b" },
    { input_hash: "different" }, { algorithm_version: "c02-v1" }, { data_cutoff: "2026-10-02T00:00:00Z" },
  ])("refuses a run incompatible with the selected bundle: %j", async change => {
    backend(table => table === "c02_runs" ? [{ ...run, ...change }] : [profile]);
    mount(); await screen.findByText(/Contexto histórico indisponível/);
    expect(mocks.from).not.toHaveBeenCalledWith("tenant_value_profiles");
  });
  it.each([{ version: 2 }, { tenant_id: "tenant-b" }, { id: "profile-current" }, { status: "draft" }, { approved_at: null }])(
    "does not substitute an incompatible or unapproved profile: %j", async change => {
      backend(table => table === "c02_runs" ? [run] : [{ ...profile, ...change }]);
      mount(); await screen.findByText(/Contexto histórico indisponível/);
      expect(screen.queryByText("Promessa histórica")).not.toBeInTheDocument();
    },
  );
  it("reports read failures without leaking the server message or substituting current data", async () => {
    backend(() => Promise.reject(new Error("private internal error")));
    mount(); await screen.findByRole("alert");
    expect(screen.queryByText(/private internal error/)).not.toBeInTheDocument();
    expect(screen.queryByText("Promessa histórica")).not.toBeInTheDocument();
  });
  it.each(["tenant", "subject", "run"])("isolates a positively completed late read after changing %s", async kind => {
    let complete!: (v: unknown) => void;
    const pending = new Promise(resolve => { complete = resolve; });
    backend((table, filters) => {
      if (table === "c02_runs") return filters["tenant_id"] === "tenant-a" && filters["subject_id"] === "subject-a" && filters["id"] === "run-a" ? [run] : [];
      return pending;
    });
    const view = mount();
    // Confirm that the old request reached the profile read before changing identity.
    await waitFor(() => expect(mocks.calls.some(c => c.table === "tenant_value_profiles")).toBe(true));
    view.change(kind === "tenant" ? "tenant-b" : "tenant-a", kind === "subject" ? "subject-b" : "subject-a",
      kind === "run" ? { ...bundle, id: "bundle-b", run_id: "run-b" } : bundle);
    await screen.findByText(/Contexto histórico indisponível/);
    await act(async () => { complete([profile]); await pending; });
    await waitFor(() => expect(view.qc.getQueryState(["t", "tenant-a", "value_context", "subject-a", "run-a", "bundle-a"])?.status).toBe("success"));
    expect(screen.queryByText("Promessa histórica")).not.toBeInTheDocument();
    expect(screen.getByText(/Contexto histórico indisponível/)).toBeInTheDocument();
  });
});
