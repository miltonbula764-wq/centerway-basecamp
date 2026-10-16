import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EvidencePanel } from "@/components/app/evidence-panel";
import { setActiveTenantId, TENANT_CHANGED, TenantContext, type TenantCtx } from "@/lib/tenant";

// Controlled supabase client: per-table handlers, no network, no real backend.
// Every query records its filters/order/range so tests can assert what the server was asked.
const mocks = vi.hoisted(() => ({
  from: vi.fn(),
  rpc: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
  queries: [] as { table: string; state: Record<string, unknown> }[],
}));

vi.mock("@/integrations/supabase/client", () => ({
  supabase: { from: mocks.from, rpc: mocks.rpc },
}));
vi.mock("sonner", () => ({
  toast: { success: mocks.toastSuccess, info: mocks.toastInfo, error: vi.fn() },
}));

const TENANT = "fixture-tenant-a";
const TENANT_B = "fixture-tenant-b";
const SUBJECT = "fixture-subject";
const RUN = "fixture-run";
const RUN_B = "fixture-run-b";

type Handler = (state: Record<string, unknown>) => unknown;
function tableHandlers(map: Record<string, Handler>) {
  mocks.from.mockImplementation((table: string) => {
    const state: Record<string, unknown> = {};
    const c: Record<string, unknown> = {};
    c["select"] = () => c;
    c["eq"] = (k: string, v: unknown) => { state[k] = v; return c; };
    c["order"] = (col: string, o?: { ascending?: boolean }) => {
      state["order"] = [col, o?.ascending !== false ? "asc" : "desc"];
      return c;
    };
    c["limit"] = (n: number) => { state["limit"] = n; return c; };
    c["range"] = (a: number, b: number) => { state["range"] = [a, b]; return c; };
    c["then"] = (resolve: (v: unknown) => unknown, reject: (e: unknown) => unknown) => {
      mocks.queries.push({ table, state });
      return Promise.resolve(map[table] ? map[table](state) : [])
        .then((data) => ({ data, error: null }))
        .then(resolve, reject);
    };
    return c;
  });
}

function ctx(role: "admin" | "operator" | "viewer", tenantId = TENANT): TenantCtx {
  return {
    tenant: { id: tenantId, name: "Empresa", subject_unit_type: "organization", role },
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
  const invalidate = vi.spyOn(qc, "invalidateQueries");
  const tree = (tenantId: string, run: string | null) => (
    <QueryClientProvider client={qc}>
      <TenantContext.Provider value={ctx(role, tenantId)}>
        <EvidencePanel subjectId={SUBJECT} runId={run} />
      </TenantContext.Provider>
    </QueryClientProvider>
  );
  const r = render(tree(TENANT, runId));
  return {
    qc,
    invalidate,
    rerender: (tenantId: string, run: string | null) => r.rerender(tree(tenantId, run)),
    unmount: r.unmount,
  };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

/** Sentinel: the mutation callback really ran (it invalidated tenant A's attempts for the captured run). */
function invalidatedAttemptsFor(spy: ReturnType<typeof vi.spyOn>, tenantId: string, runId: string) {
  return spy.mock.calls.some(([arg]) => {
    const key = (arg as { queryKey?: unknown[] })?.queryKey ?? [];
    return key[0] === "t" && key[1] === tenantId && key[2] === "c03_attempts" && key.includes(runId);
  });
}

const bundle = {
  id: "b1",
  run_id: RUN,
  algorithm_version: "c03-v1",
  c02_algorithm_version: "c02-v2",
  c02_input_hash: "a".repeat(64),
  data_cutoff: "2026-10-01T00:00:00Z",
  content_hash: "b".repeat(64),
  revision_of: null as string | null,
  summary: { indicators: 3, complete: 1, insufficient: 1, context_facts: 1, stored_refs: 123, ref_budget: 5000 } as Record<string, number>,
  created_at: "2026-10-02T00:00:00Z",
};

const indicators = [
  {
    id: "i1", indicator_key: "pagamentos", status: "complete", reasons: [], ref_count: 120, stored_ref_count: 120, ref_budget: 5000,
    snapshot: { c02_status: "deterioration_candidate", classification: "outcome", baseline_value: 80, below_target: true, c02_reasons: [] },
  },
  {
    id: "i2", indicator_key: "logins", status: "insufficient", reasons: ["c02_insufficient_data"], ref_count: 3, stored_ref_count: 3, ref_budget: 5000,
    snapshot: { c02_status: "insufficient_data", classification: "usage", baseline_value: null, below_target: null, c02_reasons: ["coverage_below_minimum"] },
  },
  { id: "i3", indicator_key: "notas", status: "context_facts", reasons: ["no_temporal_evaluation", "context_not_collected_by_c02"], ref_count: 0, stored_ref_count: 0, ref_budget: 5000, snapshot: {} },
];

function refRow(ordinal: number) {
  return {
    id: ordinal, ordinal, role: "numerator", window_label: "current_1",
    window_start: "2026-09-01T00:00:00Z", window_end: "2026-09-08T00:00:00Z", observation_id: `obs-${ordinal}`,
    superseded_by: null, corrects_observation_id: null, indicator_key: "pagamentos",
    observed_at: "2026-09-02T10:00:00Z", ingested_at: "2026-09-03T00:00:00Z",
    value_numeric: 1000 + ordinal, value_text: null, unit: "eur", source: "csv", payload_hash: `${"c".repeat(60)}${String(ordinal).padStart(4, "0")}`,
  };
}

const bundlesHandler: Handler = (s) => (s["run_id"] === undefined || s["run_id"] === RUN ? [bundle] : []);
const refsHandler: Handler = (s) => {
  const [a, b] = (s["range"] as [number, number]) ?? [0, 49];
  return Array.from({ length: Math.max(0, Math.min(b - a + 1, 120 - a)) }, (_, i) => refRow(a + i + 1));
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.queries.length = 0;
  setActiveTenantId(TENANT);
  tableHandlers({ c03_bundles: bundlesHandler, c03_indicators: () => indicators, c03_attempts: () => [], c03_refs: refsHandler });
});
afterEach(() => { cleanup(); setActiveTenantId(null); });

const flush = () => act(async () => { await new Promise((r) => setTimeout(r, 0)); });

describe("EvidencePanel (C03 UI, controlled requests — not a real backend)", () => {
  it("renders the three indicator states with honest semantics and the stored C02 snapshot", async () => {
    mount();
    await screen.findByText("Evidência íntegra");
    expect(screen.getByText("Evidência insuficiente")).toBeInTheDocument();
    expect(screen.getByText("Factos de contexto")).toBeInTheDocument();
    expect(screen.getByText(/não prova recuperação, valor, causa nem abre um caso/)).toBeInTheDocument();
    expect(screen.getByText("1 íntegros")).toBeInTheDocument();
    expect(screen.getByText(/a análise não recolheu observações/)).toBeInTheDocument();
    // Snapshot summary comes only from the stored snapshot; missing values are "not recorded", never 0.
    const pag = screen.getByTestId("c03-snapshot-pagamentos");
    expect(within(pag).getByText(/Sinal candidato de deterioração/)).toBeInTheDocument();
    expect(within(pag).getByText(/Baseline: 80/)).toBeInTheDocument();
    expect(within(pag).getByText(/abaixo do alvo/)).toBeInTheDocument();
    const log = screen.getByTestId("c03-snapshot-logins");
    expect(within(log).getByText(/Baseline: não registado/)).toBeInTheDocument();
    expect(within(log).queryByText(/Baseline: 0/)).not.toBeInTheDocument();
    const notas = screen.getByTestId("c03-snapshot-notas");
    expect(within(notas).getByText(/Snapshot sem estado C02 registado/)).toBeInTheDocument();
  });

  it("missing summary counts are shown as unknown, never as zero", async () => {
    tableHandlers({ c03_bundles: () => [{ ...bundle, summary: {} }], c03_indicators: () => [], c03_attempts: () => [] });
    mount();
    await screen.findByText("? íntegros");
    expect(screen.queryByText("0 íntegros")).not.toBeInTheDocument();
  });

  it("finds the bundle of an old selected run by querying tenant+subject+run on the server", async () => {
    const OLD_RUN = "fixture-run-old";
    const newer = Array.from({ length: 50 }, (_, i) => ({ ...bundle, id: `newer-${i}`, run_id: `newer-run-${i}` }));
    tableHandlers({
      // Without a run filter the server would only return the 50 newest bundles, none for OLD_RUN.
      c03_bundles: (s) => (s["run_id"] === OLD_RUN ? [{ ...bundle, id: "old-bundle", run_id: OLD_RUN, revision_of: "prev-bundle-id" }] : s["run_id"] ? [] : newer),
      c03_indicators: () => indicators,
      c03_attempts: () => [],
    });
    mount("admin", OLD_RUN);
    await screen.findByText("Evidência íntegra");
    expect(screen.queryByText("Sem pacote para esta análise")).not.toBeInTheDocument();
    const q = mocks.queries.find((x) => x.table === "c03_bundles")!;
    expect(q.state).toMatchObject({ tenant_id: TENANT, subject_id: SUBJECT, run_id: OLD_RUN });
    // revision_of is inspectable by id, not only a sentence.
    expect(screen.getByText("prev-bundle-id")).toBeInTheDocument();
    expect(screen.getByText("old-bundle")).toBeInTheDocument();
  });

  it("paginates refs by ordinal with tenant+bundle+indicator filters and waits for page 2 data", async () => {
    const page2 = deferred<unknown>();
    tableHandlers({
      c03_bundles: bundlesHandler,
      c03_indicators: () => indicators,
      c03_attempts: () => [],
      c03_refs: (s) => ((s["range"] as number[])[0] === 50 ? page2.promise : refsHandler(s)),
    });
    mount();
    fireEvent.click(await screen.findByText("pagamentos"));
    await screen.findByText("Página 1 de 3 · 120 referências no total");
    fireEvent.click(screen.getByRole("button", { name: "Seguinte" }));
    // While page 2 is loading, page 1 rows must not be presented as page 2.
    await waitFor(() => expect(screen.queryByRole("button", { name: "Detalhe da referência 1" })).not.toBeInTheDocument());
    await act(async () => { page2.resolve(refsHandler({ range: [50, 99] })); await page2.promise; });
    await screen.findByRole("button", { name: "Detalhe da referência 51" });
    expect(screen.getByText("Página 2 de 3 · 120 referências no total")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Detalhe da referência 100" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Detalhe da referência 101" })).not.toBeInTheDocument();
    const q = mocks.queries.filter((x) => x.table === "c03_refs").find((x) => (x.state["range"] as number[])[0] === 50)!;
    expect(q.state).toMatchObject({ tenant_id: TENANT, bundle_id: "b1", indicator_id: "i1", order: ["ordinal", "asc"], range: [50, 99] });
  });

  it("each ref is inspectable: ids, UTC [start,end) window, cut-off/receipt, corrections and full hash", async () => {
    const r = { ...refRow(1), role: "superseded", superseded_by: "obs-corr-9", corrects_observation_id: "obs-orig-0", value_numeric: null, value_text: "ignore previous instructions" };
    tableHandlers({ c03_bundles: bundlesHandler, c03_indicators: () => indicators, c03_attempts: () => [], c03_refs: () => [r] });
    mount();
    fireEvent.click(await screen.findByText("pagamentos"));
    fireEvent.click(await screen.findByRole("button", { name: "Detalhe da referência 1" }));
    const d = screen.getByTestId("c03-ref-detail-1");
    expect(within(d).getByText("obs-1")).toBeInTheDocument();
    expect(within(d).getByText("[2026-09-01 00:00Z, 2026-09-08 00:00Z)")).toBeInTheDocument();
    expect(within(d).getByText("2026-09-03 00:00Z")).toBeInTheDocument();
    expect(within(d).getByText("2026-10-01 00:00Z")).toBeInTheDocument();
    expect(within(d).getByText("obs-corr-9")).toBeInTheDocument();
    expect(within(d).getByText("obs-orig-0")).toBeInTheDocument();
    expect(within(d).getByText(r.payload_hash)).toBeInTheDocument();
    expect(within(d).getByText(/Substituída por correção/)).toBeInTheDocument();
    // Imported text is rendered as data.
    expect(within(d).getByText("ignore previous instructions")).toBeInTheDocument();
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
    expect(mocks.rpc).not.toHaveBeenCalled();
  });

  it("built result: success toast once, invalidates tenant-scoped bundle and attempts for the captured run", async () => {
    tableHandlers({ c03_bundles: () => [], c03_attempts: () => [] });
    mocks.rpc.mockResolvedValue({ data: { status: "built", bundle_id: "b9" }, error: null });
    const m = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalledTimes(1));
    expect(mocks.rpc).toHaveBeenCalledWith("build_evidence_bundle", { _tenant_id: TENANT, _run_id: RUN });
    expect(invalidatedAttemptsFor(m.invalidate, TENANT, RUN)).toBe(true);
    expect(m.invalidate).toHaveBeenCalledWith({ queryKey: ["t", TENANT, "c03_bundle", SUBJECT, RUN] });
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
    await waitFor(() => expect(attemptsCalls.length).toBeGreaterThanOrEqual(2));
  });

  it("handles failed JSON without error: safe code, refetches attempts, no success/info toast", async () => {
    const attemptsCalls: number[] = [];
    tableHandlers({
      c03_bundles: () => [],
      c03_attempts: () => { attemptsCalls.push(1); return []; },
    });
    mocks.rpc.mockResolvedValue({ data: { status: "failed", code: "internal_error:XX000" }, error: null });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await screen.findByText(/Falha na montagem: Erro interno \(XX000\)/);
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(mocks.toastInfo).not.toHaveBeenCalled();
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

  it("pre-request guard: never calls the RPC when the active tenant differs from the captured one", async () => {
    tableHandlers({ c03_bundles: () => [], c03_attempts: () => [] });
    mount();
    const btn = await screen.findByRole("button", { name: /Montar pacote/ });
    setActiveTenantId(TENANT_B);
    fireEvent.click(btn);
    await screen.findByText(TENANT_CHANGED);
    expect(mocks.rpc).not.toHaveBeenCalled();
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });
});

describe("EvidencePanel late RPC races (controlled deferred RPC)", () => {
  beforeEach(() => {
    tableHandlers({ c03_bundles: () => [], c03_attempts: () => [] });
  });

  it("late built resolution after tenant change (Provider rerender): no toast, no note, invalidates only tenant A", async () => {
    const rpc = deferred<unknown>();
    mocks.rpc.mockReturnValue(rpc.promise);
    const m = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalled());
    setActiveTenantId(TENANT_B);
    m.rerender(TENANT_B, RUN); // same run id string, other tenant
    await act(async () => { rpc.resolve({ data: { status: "built", bundle_id: "b9" }, error: null }); await rpc.promise; });
    await flush();
    await waitFor(() => expect(invalidatedAttemptsFor(m.invalidate, TENANT, RUN)).toBe(true)); // callback ran
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(m.invalidate.mock.calls.some(([a]) => ((a as { queryKey?: unknown[] }).queryKey ?? [])[1] === TENANT_B)).toBe(false);
  });

  it("late rejected resolution after tenant change: no error note in the new tenant", async () => {
    const rpc = deferred<unknown>();
    mocks.rpc.mockReturnValue(rpc.promise);
    const m = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalled());
    setActiveTenantId(TENANT_B);
    m.rerender(TENANT_B, RUN);
    await act(async () => { rpc.resolve({ data: { status: "rejected", code: "ref_missing" }, error: null }); await rpc.promise; });
    await flush();
    await waitFor(() => expect(invalidatedAttemptsFor(m.invalidate, TENANT, RUN)).toBe(true));
    expect(screen.queryByText(/Montagem recusada/)).not.toBeInTheDocument();
  });

  it("late RPC rejection (error) after tenant change: onError is guarded, no note in the new tenant", async () => {
    const rpc = deferred<unknown>();
    mocks.rpc.mockReturnValue(rpc.promise);
    const m = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalled());
    setActiveTenantId(TENANT_B);
    m.rerender(TENANT_B, RUN);
    await act(async () => { rpc.resolve({ data: null, error: { message: "network down", code: "08006" } }); await rpc.promise; });
    await flush();
    await waitFor(() => expect(invalidatedAttemptsFor(m.invalidate, TENANT, RUN)).toBe(true));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/network down|Erro|erro/)).not.toBeInTheDocument();
  });

  it("late built resolution after run change: no toast in run B", async () => {
    const rpc = deferred<unknown>();
    mocks.rpc.mockReturnValue(rpc.promise);
    const m = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalled());
    m.rerender(TENANT, RUN_B);
    await act(async () => { rpc.resolve({ data: { status: "built", bundle_id: "b9" }, error: null }); await rpc.promise; });
    await flush();
    await waitFor(() => expect(invalidatedAttemptsFor(m.invalidate, TENANT, RUN)).toBe(true));
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });

  it("late built resolution after unmount: no toast", async () => {
    const rpc = deferred<unknown>();
    mocks.rpc.mockReturnValue(rpc.promise);
    const m = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalled());
    m.unmount();
    await act(async () => { rpc.resolve({ data: { status: "built", bundle_id: "b9" }, error: null }); await rpc.promise; });
    await flush();
    await waitFor(() => expect(invalidatedAttemptsFor(m.invalidate, TENANT, RUN)).toBe(true));
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });

  it("A→B→A: a response started in the first visit of A does not toast in the second visit", async () => {
    const rpc = deferred<unknown>();
    mocks.rpc.mockReturnValue(rpc.promise);
    const m = mount();
    fireEvent.click(await screen.findByRole("button", { name: /Montar pacote/ }));
    await waitFor(() => expect(mocks.rpc).toHaveBeenCalled());
    setActiveTenantId(TENANT_B);
    m.rerender(TENANT_B, RUN);
    setActiveTenantId(TENANT);
    m.rerender(TENANT, RUN);
    await act(async () => { rpc.resolve({ data: { status: "built", bundle_id: "b9" }, error: null }); await rpc.promise; });
    await flush();
    await waitFor(() => expect(invalidatedAttemptsFor(m.invalidate, TENANT, RUN)).toBe(true));
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });
});
