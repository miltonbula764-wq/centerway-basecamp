// Controlled query races. Real authentication/RLS are covered by the disposable HTTP and browser suites.
import { afterEach, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { cycleHistoryQuery } from "@/lib/operational-cycles";
const mocks = vi.hoisted(() => ({ rpc: vi.fn() }));
vi.mock("@/integrations/supabase/client", () => ({ supabase: { rpc: mocks.rpc } }));
afterEach(() => vi.resetAllMocks());
const cycle = { tenant_id: "A", case_id: "case", id: "cycle", number: 2 };
const history = {
  tenant_id: "A",
  subject_id: "subject",
  case_id: "case",
  case_version: 8,
  current: cycle,
  selected: cycle,
  cycles: [cycle],
  events: [],
  heads: {},
  has_more_events: false,
  has_more_cycles: false,
};
it("rejects history, cycle and event identities belonging to another company, case or subject", async () => {
  for (const data of [
    { ...history, tenant_id: "B" },
    { ...history, current: { ...cycle, case_id: "foreign" } },
    { ...history, selected: { ...cycle, tenant_id: "B" } },
    { ...history, events: [{ tenant_id: "A", case_id: "case", subject_id: "foreign" }] },
    { ...history, heads: { approve: { tenant_id: "B", case_id: "case", subject_id: "subject" } } },
  ]) {
    mocks.rpc.mockReturnValue({ abortSignal: () => Promise.resolve({ data, error: null }) });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    await expect(
      client.fetchQuery(cycleHistoryQuery("A", "subject", "case", 8, null, null, -1)),
    ).rejects.toThrow(/Identidade do histórico/);
    client.clear();
  }
});
it("keys pagination by tenant, case, version and cycle; forwards cancellation and ignores late history", async () => {
  let finish: (x: unknown) => void = () => {};
  let signal: AbortSignal | undefined;
  mocks.rpc.mockReturnValue({
    abortSignal: (s: AbortSignal) => {
      signal = s;
      return new Promise((resolve) => (finish = resolve));
    },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const options = cycleHistoryQuery("A", "subject", "case", 8, "cycle", 3, 10);
  expect(options.queryKey.slice(0, 2)).toEqual(["t", "A"]);
  const pending = client.fetchQuery(options);
  const failure = expect(pending).rejects.toThrow();
  await client.cancelQueries({ queryKey: ["t", "A"] });
  client.removeQueries({ queryKey: ["t", "A"] });
  finish({ data: history, error: null });
  await failure;
  expect(signal?.aborted).toBe(true);
  expect(client.getQueryCache().findAll({ queryKey: ["t", "A"] })).toHaveLength(0);
  expect(mocks.rpc).toHaveBeenCalledWith(
    "operational_cycle_history",
    expect.objectContaining({
      _tenant_id: "A",
      _case_id: "case",
      _cycle_id: "cycle",
      _before_cycle: 3,
      _after_event: 10,
    }),
  );
  client.clear();
});
