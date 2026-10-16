import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EvidencePanel } from "@/components/app/evidence-panel";
import { setActiveTenantId, TenantContext, type TenantCtx } from "@/lib/tenant";

// Controlled supabase client: per-table handlers, no network, no real backend.
const mocks = vi.hoisted(() => ({
  from: vi.fn(),
  rpc: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
}));

vi.mock("@/integrations/supabase/client", () => ({
  supabase: { from: mocks.from, rpc: mocks.rpc },
}));
vi.mock("sonner", () => ({
  toast: { success: mocks.toastSuccess, info: mocks.toastInfo, error: vi.fn() },
}));

const TENANT = "fixture-tenant";
const SUBJECT = "fixture-subject";
const RUN = "fixture-run";

function tableHandlers(map: Record<string, (args: Record<string, unknown>) => unknown>) {
  mocks.from.mockImplementation((table: string) => {
    const state: Record<string, unknown> = {};
    const c: Record<string, unknown> = {};
    for (const m of ["select"]) c[m] = () => c;
    c.eq = (k: string, v: unknown) => { state[k] = v; return c; };
    c["order"] = (col: string, o: { ascending?: boolean }) => {
      state["order"] = [col, o.ascending !== false ? "asc" : "desc"];
      return c;
    };
    c["limit"] = (n: number) => {
      state["limit"] = n;
      return c;
    };
    c["range"] = (a: number, b: number) => {
      state["range"] = [a, b];
      return c;
    };
    c["then"] = (resolve: (v: unknown) => unknown) =>
      Promise.resolve({ data: map[table] ? map[table](state) : [], error: null }).then(resolve);
    return c;
  });
}

function ctx(role: "admin" | "operator" | "viewer"): TenantCtx {
  return {
    tenant: { id: TENANT, name: "Empresa", subject_unit_type: "organization", role },
    tenants: [],
    user: { id: "u1", email: "f@example.invalid" },
    switchTenant: () => {},
    signOut: async () => {},
    canWrite: role === "admin" || role === "operator",
    isAdmin: role === "admin",
  };
}

function mount(role: "admin" | "viewer" = "admin", runId: string | null = RUN) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <TenantContext.Provider value={ctx(role)}>
        <EvidencePanel subjectId={SUBJECT} runId={runId} />
      </TenantContext.Provider>
    </QueryClientProvider>,
  );
  return qc;
}

const bundle = {
  id: "b1",
  run_id: RUN,
  algorithm_version: "c03-v1",
  c02_algorithm_version: "c02-v2",
  c02_input_hash: "a".repeat(64),
  data_cutoff: "2026-10-01T00:00:00Z",
  content_hash: "b".repeat(64),
  revision_of: null,
  summary: { indicators: 3, complete: 1, insufficient: 1, context_facts: 1, stored_refs: 120, ref_budget: 5000 },
  created_at: "2026-10-02T00:00:00Z",
};

const indicators = [
  { id: "i1", indicator_key: "pagamentos", status: "complete", reasons: [], ref_count: 120, stored_ref_count: 120, ref_budget: 5000, snapshot: {} },
  { id: "i2", indicator_key: "logins", status: "insufficient", reasons: ["c02_insufficient_data"], ref_count: 3, stored_ref_count: 3, ref_budget: 5000, snapshot: {} },
  { id: "i3", indicator_key: "notas", status: "context_facts", reasons: ["no_temporal_evaluation", "context_not_collected_by_c02"], ref_count: 0, stored_ref_count: 0, ref_budget: 5000, snapshot: {} },
];

function refRow(ordinal: number) {
  return {
    id: ordinal, ordinal, role: "numerator", window_label: "current_1",
    window_start: null, window_end: null, observation_id: `obs-${ordinal}`,
    superseded_by: null, corrects_observation_id: null, indicator_key: "pagamentos",
    observed_at: "2026-09-15T00:00:00Z", ingested_at: "2026-09-16T00:00:00Z",
    value_numeric: ordinal, value_text: null, unit: "eur", source: "csv", payload_hash: "c".repeat(64),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  setActiveTenantId(TENANT);
  tableHandlers({
    c03_bundles: () => [bundle],
    c03_indicators: () => indicators,
    c03_attempts: () => [],
    c03_refs: (s) => {
      const [a, b] = (s["range"] as [number, number]) ?? [0, 49];
      return Array.from({ length: Math.min(b - a + 1, 120 - a) }, (_, i) => refRow(a + i + 1));
    },
  });
});
afterEach(() => { cleanup(); setActiveTenantId(null); });

describe("EvidencePanel (C03 UI, controlled requests — not a real backend)", () => {
  it("renders the three indicator states with honest semantics", async () => {
    mount();
    await screen.findByText("Evidência íntegra");
    expect(screen.getByText("Evidência insuficiente")).toBeInTheDocument();
    expect(screen.getByText("Factos de contexto")).toBeInTheDocument();
    expect(screen.getByText(/não prova recuperação, valor, causa nem abre um caso/)).toBeInTheDocument();
    expect(screen.getByText("1 íntegros")).toBeInTheDocument();
    expect(screen.getByText(/a análise não recolheu observações/)).toBeInTheDocument();
  });

  it("paginates refs deterministically by ordinal and never presents a page as the total", async () => {
    mount();
    fireEvent.click(await screen.findByText("pagamentos"));
    await screen.findByText("Página 1 de 3 · 120 referências no total");
    fireEvent.click(screen.getByRole("button", { name: "Seguinte" }));
    await screen.findByText("Página 2 de 3 · 120 referências no total");
    // deterministic: page 2 starts at ordinal 51 (ordinal and value cells both render it)
    expect(screen.getAllByText("51").length).toBeGreaterThan(0);
    expect(screen.queryByText("1", { selector: "td" })).not.toBeInTheDocument();
  });

  it("explains ref budget exceeded without showing a partial bundle as complete", async () => {
    tableHandlers({
      c03_bundles: () => [{ ...bundle, summary: { ...bundle.summary, complete: 0, insufficient: 1, stored_refs: 0 } }],
      c03_indicators: () => [{ ...indicators[0], status: "insufficient", reasons: ["ref_budget_exceeded"], ref_count: 6000, stored_ref_count: 0 }],
      c03_attempts: () => [],
    });
    mount();
    await screen.findByText(/6000 referências exigidas · 0 guardadas/);
    fireEvent.click(screen.getByText("pagamentos"));
    await screen.findByText(/nenhuma foi guardada para não apresentar um pacote parcial como completo/);
  });

  it("viewer can read but never sees the build button", async () => {
    mount("viewer");
    await screen.findByText("Evidência íntegra");
    expect(screen.queryByRole("button", { name: /Montar pacote/ })).not.toBeInTheDocument();
  });

  it("handles rejected JSON without error: shows the code, refetches attempts, no success toast", async () => {
    const attemptsCalls: number[] = [];
    tableHandlers({
      c03_bundles: () => [],
      c03_attempts: () => { attemptsCalls.push(1); return [{ id: "t1", status: "rejected", code: "ref_after_cutoff", bundle_id: null, created_at: "2026-10-02T00:00:00Z" }]; },
    });
    mocks.rpc.mockResolvedValue({ data: { status: "rejected", code: "ref_after_cutoff" }, error: null });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await screen.findByText(/Montagem recusada: Uma observação foi importada depois da data de corte/);
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.rpc).toHaveBeenCalledWith("build_evidence_bundle", { _tenant_id: TENANT, _run_id: RUN });
    await waitFor(() => expect(attemptsCalls.length).toBeGreaterThanOrEqual(2));
  });

  it("reused result shows info, not success", async () => {
    tableHandlers({ c03_bundles: () => [], c03_attempts: () => [] });
    mocks.rpc.mockResolvedValue({ data: { status: "reused", bundle_id: "b1" }, error: null });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.toastInfo).toHaveBeenCalled());
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });

  it("a late RPC resolution after tenant change shows no success toast", async () => {
    let resolveRpc: (v: unknown) => void;
    mocks.rpc.mockReturnValue(new Promise((r) => { resolveRpc = r; }));
    tableHandlers({ c03_bundles: () => [], c03_attempts: () => [] });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    // Tenant changes while the RPC is in flight.
    setActiveTenantId("other-tenant");
    resolveRpc!({ data: { status: "built", bundle_id: "b9" }, error: null });
    await waitFor(() => expect(mocks.toastSuccess).not.toHaveBeenCalled());
  });
});
